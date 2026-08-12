"""#977 -- les CINQ faces DECISION du lot (WorldEaters / Genestealer / Death Guard / Black
Templars), sur UN SEUL montage co-injecte.

CE QUE CETTE GARDE VERROUILLE, et pourquoi chaque cran existe.

A. **Les trois NonComparable sont PORTES et leur utilite est EXACTE, position par position.**
   `ncEvaluate` invoque `EvaluateNonComparable(caster, UnitPosition(P))` -- le corps NATIF, par
   position -- et le port expose la MEME unite (`playbook.evaluate_at`). La confrontation n'est
   donc pas « le port et le natif choisissent la meme action » (trop grossier : un argmax peut
   coincider par chance) mais « ils rendent la MEME utilite sur les 15 / 24 positions du sweep ».

B. **L'ORDRE du selecteur est le VOISINAGE NATIF de la tuile, et le caster self-cast y est ajoute
   EN DERNIER.** Les deux faits decident la CIBLE emise -- `1141` ne garde que
   `Enumerable.First(targets)`. Ils sont MESURES : la liste reconstruite par le port egale, element
   par element, le `fromHere` que le RPC publie, sur les TROIS abilities. C'est ce cran qui autorise
   a appliquer la meme regle aux tuiles de MOVE, ou aucune vue RPC n'existe.

C. **`1043` n'est jugeable QUE par la decision native.** `ncEvaluate` decode `Bucket+0x20`, or
   `NonComparablePlaybook<T>$$GenerateBucketWithMultipleStrategies` n'ecrit JAMAIS ce champ (il
   passe par `AddActionToBucket` -> sous-bucket de la `SortedList` a `+0x28`). Le capteur rend donc
   `bucket: empty` partout, MEME quand une action existe -- et `aiDryRunAllUnits` la montre. La
   garde exige que le probe DIAGNOSTIQUE cette cecite (`capteurAveugle`) au lieu de la lire comme
   une divergence : c'est exactement « l'absence d'un EVENEMENT ne prouve RIEN ».

D. **`1168 EntropyCannons` n'a RIEN a porter, et ce n'est pas un aveu.** Son
   `MakeDamagePredictions` natif est la forme CANONIQUE (`GetDamage` / `GetHits` /
   `GetDamageProfile` de base) : le chemin GENERIQUE du port EST son mirror. La garde le PROUVE
   (4 cibles, bit-exact) au lieu de le supposer -- sans quoi « rien a faire » serait indistinguable
   de « pas regarde ».

E. **Les contre-epreuves MORDENT, et les deux qui ne mordent pas sont NOMMEES.** Une passe verte
   sans mutation mordante ne prouve rien. Les deux muettes restantes disent le meme fait : la
   STRATEGIE 2 de `1043` n'est pas exercee par ce montage (residus `#977-r3` / `#977-r4`).

Mesure : `probe_977_faces_decision_kit.py`. ASCII only.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        'scripts/python/probe_977_faces_decision_kit.py',
    ),
    "build": False,
    "toujours": False,
    "raison": "UN seul chemin a declarer, et c'est le probe : `probe_486r15 --proposer` mesure que "
              "les 585 autres modules de la fermeture d'imports sortent DEJA de la cascade derivee "
              "du foyer (#531), donc les redeclarer serait du bruit. Le probe, lui, n'est importe "
              "par aucun module d'`engine/**` -- il porte le MONTAGE (positions `--place`, roster, "
              "board), les etages de confrontation et la table des contre-epreuves : le toucher "
              "change ce que la garde MESURE sans toucher au code porte, et rien d'autre ne le "
              "verrait. `build: False` : aucune valeur n'est figee depuis le binaire -- les "
              "utilites (3/2/1), le poids `MIGHTFROMBELOW_ExistingAdjacentDecoy` (3) et les bornes "
              "de degat sont RELEVEES LIVE des deux cotes a chaque passe, jamais comparees a un "
              "litteral. `toujours: False` : le fichier monte DEUX runners (montage co-injecte + "
              "montage Decoy) et coute ~170 s -- le rejouer a chaque passe couterait plus que ce "
              "que borne sa cascade.",
}

import sys                                                  # noqa: E402
from pathlib import Path                                    # noqa: E402

import pytest                                               # noqa: E402

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_977_faces_decision_kit as P977                 # noqa: E402
from engine.playbook.base import REGISTRY                   # noqa: E402
from engine.playbook.noncomparable import PLAYBOOKS         # noqa: E402

_NC = (1131, 1141, 1043)


@pytest.fixture(scope="module")
def v977():
    sf = PYDIR.parents[1] / "logs" / "t977.json"
    return P977.run(state_file=str(sf), verbose=False)


# --- OFFLINE : le port existe, et il est ou il doit etre ----------------------------------------

def test_les_trois_noncomparable_sont_au_registre_nc():
    """Base LUE dans `frida/classes.tsv` : `NonComparablePlaybook`1` pour les trois. Les inscrire
    dans `playbook.REGISTRY` (le tier COMPARABLE) serait un port MORT."""
    for aid in _NC:
        assert aid in PLAYBOOKS, "%d absente de noncomparable.PLAYBOOKS" % aid
        assert aid not in REGISTRY, "%d inscrite a tort au registre COMPARABLE" % aid


def test_min_utility_1043_est_moins_l_infini():
    """`Bucket<T>..ctor` a UN argument (`GenerateBucketWithMultipleStrategies`) + AUCUN `.cctor` de
    classe => `minUtility.HasValue == false`. Le defaut `0.0` de la classe de base TUERAIT ce
    playbook en silence : son utilite est un ecart d'utilite de TUILE, nul sur un plateau plat."""
    assert PLAYBOOKS[1043].MIN_UTILITY == float("-inf")


def test_min_utility_des_deux_worldeaters_vaut_un():
    """Leur `.cctor` propre ecrit `Fix64(1)` et leur `EvaluateNonComparable` relit CE static pour
    le `Bucket<T>..ctor` a TROIS arguments. Le `Fix64(10)` de `ComparablePlaybook<T>$$.cctor`
    (`static_threshold_gate`) ne les concerne pas : cette classe n'est pas dans leur chaine."""
    assert PLAYBOOKS[1131].MIN_UTILITY == 1.0
    assert PLAYBOOKS[1141].MIN_UTILITY == 1.0


def test_1165_est_au_registre_comparable_et_override_le_terme_de_position():
    """`MightFromBelowPlaybook` a pour base `ComparablePlaybook`1` et n'a que DEUX methodes propres,
    dont une seule change quelque chose : `CalculateCasterPositionUtility` (slot +0x348)."""
    from engine.playbook.base import ComparablePlaybook
    pb = REGISTRY.get(1165)
    assert pb is not None and 1165 not in PLAYBOOKS
    assert (type(pb).calculate_caster_position_utility
            is not ComparablePlaybook.calculate_caster_position_utility)


def test_le_crochet_de_position_est_un_no_op_pour_tous_les_autres():
    """Le corps de BASE natif est `return Fix64.op_Implicit(0)`. Poser le crochet ne doit donc
    RIEN changer aux 100+ membres actuels du registre -- c'est ce qui rend l'ajout sur un foyer
    partage acceptable."""
    from engine.playbook.base import ComparablePlaybook
    override = [aid for aid, pb in REGISTRY.items()
                if type(pb).calculate_caster_position_utility
                is not ComparablePlaybook.calculate_caster_position_utility]
    assert override == [1165], "attendu 1165 SEULE, trouve %s" % override
    assert ComparablePlaybook().calculate_caster_position_utility(None, (0, 0), 0) == 0.0


# --- LIVE : le montage ---------------------------------------------------------------------------

def test_co_injection_des_cinq_porteurs(v977):
    """Cinq porteurs de QUATRE factions -- dont une MACHINE OF WAR -- dans la MEME equipe de la
    MEME bataille. C'est la condition qui rend UN montage suffisant pour les cinq."""
    co = v977["co_injection"]
    assert co["ok"], co["carriers"]
    assert all(v is not None for v in co["carriers"].values()), co["carriers"]


@pytest.mark.parametrize("aid", _NC)
def test_utilite_par_position_exacte(v977, aid):
    """L'utilite NATIVE, position par position, contre celle du port. `1043` est NON CONFRONTE ici
    -- et le probe doit le DIAGNOSTIQUER (`capteurAveugle`), pas le subir."""
    rec = v977["step2"][aid]
    if aid == 1043:
        assert rec["ok"] is None and rec["capteurAveugle"] is True, rec
        assert rec["toutesBucketsVides"] is True, rec
        return
    assert rec["ok"] is True, rec
    assert rec["utilOk"] == rec["nComparees"] >= 4, rec
    assert rec["nScoredNatif"] >= 3, "montage DEGENERE : trop peu de positions scorees natif"


@pytest.mark.parametrize("aid", _NC)
def test_ordre_du_selecteur_egale_fromHere(v977, aid):
    """Le cran qui autorise la regle « voisinage natif » aux tuiles de MOVE."""
    rec = v977["step2bis"][aid]
    assert rec["ok"] is True, rec
    assert len(rec["fromHere"]) >= 2, "montage DEGENERE : moins de 2 cibles a l'origine"


def test_le_caster_self_cast_de_1141_est_compte_et_place_en_dernier(v977):
    """`isSelfCasting = 1` + `0x800 AddCasterIfAtLeastOneTarget` : le caster ENTRE dans
    `targets.Count` (donc dans l'utilite) et il y entre EN DERNIER (donc il n'est PAS la cible
    emise tant qu'un ennemi est present)."""
    rec = v977["step2bis"][1141]
    caster = v977["co_injection"]["carriers"]["worldEightbound"]["id"]
    assert rec["fromHere"][-1] == caster, rec
    assert caster not in rec["fromHere"][:-1], rec


@pytest.mark.parametrize("aid", _NC)
def test_decision_native_egale_celle_du_port(v977, aid):
    """L'etage qui traverse le generateur ENTIER -- et le SEUL qui puisse juger `1043`."""
    rec = v977["step2ter"][aid]
    assert rec["ok"] is True, rec


@pytest.mark.parametrize("aid", (1165, 1168))
def test_prediction_generique_bit_exacte(v977, aid):
    """`MakeDamagePredictions` natif vs le chemin GENERIQUE du port, sur toutes les cibles."""
    rec = v977["step3"][aid]
    assert rec["ok"] is True, rec
    assert len(rec["events"]) >= 3, "montage DEGENERE : moins de 3 cibles confrontees"


def test_1168_na_aucune_entree_de_registre(v977):
    """« Rien a porter » est un VERDICT, et il doit rester verifiable : si un jour 1168 gagne une
    entree de registre ou un override d'entree, ce test rougit et force a re-lire le decompile."""
    from engine.playbook.prediction.abilities import (_MAKE_DMG_INPUT_OVERRIDES,
                                                      _PLAYBOOK_PROFILE_OVERRIDE,
                                                      _MAKE_DMG_SELECTOR_ONLY)
    assert 1168 not in REGISTRY and 1168 not in PLAYBOOKS
    assert 1168 not in _MAKE_DMG_INPUT_OVERRIDES
    assert 1168 not in _PLAYBOOK_PROFILE_OVERRIDE
    assert 1168 not in _MAKE_DMG_SELECTOR_ONLY


# --- LIVE : le terme de POSITION de 1165, dans son regime NON degenere ---------------------------

def test_terme_de_position_1165_non_nul_avec_des_decoys(v977):
    """Sans leurre, le terme vaut 0 PARTOUT -- le mesurer la ne prouve rien. L'etape 5 invoque
    `1179 CultDemagogue` (le SEUL invocateur de `genesSmnDecoy` du build) puis mesure."""
    rec = v977["step5"]
    assert rec["cast_1179"] is True, rec
    assert len(rec["decoys_vivants"]) >= 2, rec
    assert rec["W"] == 3, "poids `MIGHTFROMBELOW_ExistingAdjacentDecoy` du BC"
    assert rec["cpu_non_nul"], "le terme est reste nul malgre les leurres"
    assert rec["ok"] is True, rec


# --- LES CONTRE-EPREUVES : une passe verte sans mutation mordante ne prouve rien -----------------

_DOIVENT_MORDRE = (
    "1131 aoe_count -> 0 (le splash ne compte plus)",
    "1131 utilite `n` au lieu de `1 + n` (le plancher saute)",
    "1131 IsDisallowedTarget toujours VRAI (le gate mord partout)",
    "1141 self_cast=False (le caster sort du compte)",
    "1141 caster EN TETE au lieu d'EN DERNIER",
    "1141 ordre INVERSE du selecteur",
    "1043 MIN_UTILITY = 20.0 (au-dessus des utilites mesurees)",
    "1043 IsDisplaceable -> False (plus aucune cible poussable)",
    "1043 GetPushableTiles -> [] (arc arriere vide)",
)

#: Les DEUX qui ne mordent pas, et la raison -- LA MEME : la strategie 2 de `1043` n'est jamais
#: atteinte sur ce montage (la strategie 1 rend une action a chaque position ou l'ability est
#: legale). Les lister ici les rend COMPTABLES : si l'une se met a mordre, le test rougit et il
#: faudra dire pourquoi. Residus `#977-r3` (regime strategie 2) et `#977-r4` (seuil non exerce).
_MUETTES_CONNUES = (
    "1043 MIN_UTILITY = 0.0 (le defaut de la classe de base)",
    "1043 strategies PERMUTEES (la 2 avant la 1)",
)


@pytest.mark.parametrize("nom", _DOIVENT_MORDRE)
def test_contre_epreuve_mordante(v977, nom):
    rec = v977["step4"][nom]
    assert rec["mordante"] is True, "mutation MUETTE (trou de couverture) : %s" % nom


@pytest.mark.parametrize("nom", _MUETTES_CONNUES)
def test_contre_epreuve_muette_declaree(v977, nom):
    """Une muette DECLAREE reste une mesure : elle doit rester muette pour la raison ecrite, sinon
    l'inventaire des residus est perime."""
    assert v977["step4"][nom]["mordante"] is False, (
        "cette mutation MORD desormais -- le montage a change, re-lire #977-r3/#977-r4 : %s" % nom)


def test_les_deux_contre_epreuves_de_1165_mordent(v977):
    """Sur le montage DECOY (le seul ou le terme est non nul) : annuler le terme MORD, et ignorer
    le trait `Decoy` MORD aussi -- ce second cran prouve que le predicat de trait est bien LU (et
    que l'import du foyer est en forme B, sans quoi la mutation serait muette en silence)."""
    rec = v977["step5"]
    assert rec["mutation_cpu_zero_mordante"] is True, rec
    assert rec["mutation_trait_ignore_mordante"] is True, rec
