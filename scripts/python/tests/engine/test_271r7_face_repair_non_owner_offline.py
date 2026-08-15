"""#271-r7 -- la face REPAIR du dispatcher non-owner, la DERNIERE des trois.

LE BLOCAGE `etage` EST REFUTE, ET PAR UNE LECTURE, PAS PAR UN CONTOURNEMENT
---------------------------------------------------------------------------
La fiche disait : << `VoltagheistFieldPlaybook` rend `<utilitiesDatabase>.GetUtility(0x30, 0).
<slot 6>(case)`, et le `<slot 6>` d'`IUtility` n'est pas dans
`data/symbols/<build>/metadata/interface_slots.tsv` (l'interface n'y figure pas) : le canal n'est
pas etabli. Monter un dispatcher REPAIR a registre VIDE serait le patron #419. >>

C'est le TSV qui manquait, pas le slot. `probe_271r7_iutility_slots.py` le lit dans le
`global-metadata.dat` du build courant par la MEME machinerie que `probe_477r25`
(`il2cpp_metadata.locate_types`, table designee par le TYPE donc sans ambiguite d'interface) :
`IUtility` slot 6 = **`EvaluateRepair(UtilityAttackCase) -> Fix64`**, et les slots 0..8 concordent
avec la DECLARATION Il2CppDumper (le 9 est un AJOUT de ce build).

CE QUE CE FICHIER FIGE
----------------------
  1. le registre REPAIR n'est pas VIDE (sinon ce serait bien le patron #419) et il est DISJOINT
     des deux autres -- une classe inscrite deux fois doublerait son terme ;
  2. le terme est un **DOUBLEMENT** de la feuille `RepairedAmount(48)`, pas un poids BC : le corps
     ne lit AUCUNE cle, et le cliquet verifie qu'aucune cle de ce nom n'existe ;
  3. `case.Target != owner` -> rien (le porteur doit etre la CIBLE reparee) ;
  4. l'exclusion de self d'`<IterateAbilities>d__4` est INCONDITIONNELLE -- le reparateur ne pese
     jamais sa propre ability ;
  5. le pre-gate `<slot 4> || IsFriend` : `VoltagheistFieldPlaybook` porte `<slot 4> = false`
     (entree versionnee `metadata/non_owner_slot4.tsv`), donc un porteur ENNEMI est ecarte ;
  6. la degradation quand la prediction manque (`fill_hp is None`) : 0, jamais une valeur inventee.

100 % OFFLINE (l'etage 0 se SKIP si le jeu n'est pas installe -- NON MESURE, jamais un vert).
ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PY = Path(__file__).resolve().parents[2]
if str(_PY) not in sys.path:
    sys.path.insert(0, str(_PY))

from engine.entities.triggered_ability_type import TriggeredAbilityType     # noqa: E402
from engine.playbook import non_owner as NO                                 # noqa: E402
from engine.playbook import non_owner_attack as NOA                         # noqa: E402
from engine.playbook import non_owner_repair as NOR                         # noqa: E402
from engine.predict import repair_utility                                   # noqa: E402
from engine.utilities.tile import (                                         # noqa: E402
    triggered_abilities_non_owner_repair_utility)
from engine.weights import load as load_weights                             # noqa: E402

DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/playbook/non_owner_repair.py",
        "scripts/python/engine/playbook/non_owner.py",
        "scripts/python/engine/playbook/non_owner_attack.py",
        "scripts/python/engine/utilities/tile.py",
        "scripts/python/engine/utilities/repair.py",
        "scripts/python/engine/predict.py",
        "scripts/python/engine/ai/action_generators.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        # L'etage 0 relit le BINAIRE par cette machinerie.
        "scripts/python/il2cpp_metadata.py",
        "scripts/python/build_pin.py",
        "scripts/python/probe_271r7_iutility_slots.py",
        "scripts/python/probe_477r25_slots_autres_interfaces.py",
        "data/symbols/**",
    ),
    # `True` : l'etage 0 relit le `global-metadata.dat` du build.
    "build": True,
    "toujours": False,
    "raison": ("garde un registre de playbook et son dispatcher ; l'etage 0 relit le metadata du "
               "build, les autres ne lisent que les foyers ci-dessus"),
}

VF = int(TriggeredAbilityType.VoltagheistField)          # 1302


# ================================================================================================
# ETAGE 0 -- le slot d'interface, RELU dans le metadata du build courant
# ================================================================================================
def test_le_slot_6_d_IUtility_est_EvaluateRepair():
    """C'est CE fait qui refute le `BLOCAGE: etage`. `pytest.skip` si le jeu n'est pas installe."""
    import probe_271r7_iutility_slots as P
    import build_pin
    import il2cpp_metadata
    from symbols_layout import build_dir, current_build
    try:
        meta = Path(build_pin.global_metadata())
    except Exception as exc:                                                # noqa: BLE001
        pytest.skip("global-metadata absent (NON MESURE) : %s" % exc)
    methods_tsv = build_dir(current_build()) / "frida" / "methods.tsv"
    if not methods_tsv.is_file():
        pytest.skip("methods.tsv absent (NON MESURE)")
    reader = il2cpp_metadata.read(meta)
    reader.locate(il2cpp_metadata.class_method_order(methods_tsv, "%s.%s" % P.ANCRES_TYPES[0]))
    reader.locate_types([(ns, nm, il2cpp_metadata.class_method_order(methods_tsv,
                                                                    "%s.%s" % (ns, nm)))
                         for ns, nm in P.ANCRES_TYPES])
    lus = {m.slot: m.name for m in reader.type_methods("IdunBattle.AI.Utilities", "IUtility")}
    assert lus, "PAS MESURE : IUtility introuvable dans le metadata"
    assert lus.get(P.SLOT_CIBLE) == P.NOM_CIBLE, lus
    # ... et les slots 0..8 concordent avec la declaration (le 9 est un ajout de build).
    assert {s: n for s, n in lus.items() if s in P.ATTENDU} == P.ATTENDU, lus


# ================================================================================================
# ETAGE 1 -- le registre : NON VIDE et DISJOINT des deux autres
# ================================================================================================
def test_le_registre_repair_n_est_pas_vide_et_ne_recoupe_pas_les_deux_autres():
    """Un registre VIDE serait le patron #419 (du code que rien n'itere) ; une classe presente
    dans DEUX registres verserait son terme dans DEUX composites."""
    assert NOR.NON_OWNER_REPAIR_PLAYBOOKS, "registre REPAIR vide -- patron #419"
    move = set(NO.NON_OWNER_MOVE_PLAYBOOKS)
    attack = set(NOA.NON_OWNER_ATTACK_PLAYBOOKS)
    repair = set(NOR.NON_OWNER_REPAIR_PLAYBOOKS)
    assert repair & move == set(), repair & move
    assert repair & attack == set(), repair & attack
    for pb in NOR.NON_OWNER_REPAIR_PLAYBOOKS.values():
        assert pb.FACE == "REPAIR", (type(pb).__name__, pb.FACE)
        # `<slot 4>` LU dans `metadata/non_owner_slot4.tsv` : cette classe ne declare pas le getter.
        assert pb.SLOT_4 is False


def test_le_terme_ne_lit_AUCUNE_cle_BC():
    """Le corps natif ne fait pas de `getUtilityVal` : il RE-EMET la feuille `RepairedAmount(48)`.
    Une cle inventee ici serait une fausse verite (lecon #212 / #456-r1)."""
    wt = load_weights()
    for section in ("TriggeredAbilities", "TriggeredAbilitiesNonOwner"):
        for cle in ("VoltagheistField", "VOLTAGHEISTFIELD_Repair",
                    "VoltagheistField_RepairedAmount", "VoltagheistField_Repair"):
            assert not wt.sub(section, cle), (section, cle)


# ================================================================================================
# ETAGE 2 -- le dispatcher et le corps
# ================================================================================================
class _SceneDouble:
    def __init__(self, units):
        self._u = units
        self.units = [{"id": u["id"], "visualId": u.get("vis")} for u in units]
        self.vis_by_id = {u["id"]: u.get("vis") for u in units}

    def team(self, uid):
        return next((u["team"] for u in self._u if u["id"] == uid), None)

    def pos(self, uid):
        return next((u.get("pos") for u in self._u if u["id"] == uid), None)


class _CtxDouble:
    def __init__(self, units):
        self.scene = _SceneDouble(units)
        self._kits = {u["id"]: tuple(u.get("kit") or ()) for u in units}
        self.wt = load_weights()

    def live_triggered_ability_ids(self, uid):
        return list(self._kits.get(int(uid)) or ())


#: reparateur 1 (equipe 0), cible 2 (equipe 0, PORTE VoltagheistField), tiers 3 (equipe 1).
def _units(cible_porte=True, cible_team=0, caster_porte=False):
    return [{"id": 1, "vis": "admecDominus", "team": 0, "pos": (0, 0),
             "kit": (VF,) if caster_porte else ()},
            {"id": 2, "vis": "admecKataphron", "team": cible_team, "pos": (1, 0),
             "kit": (VF,) if cible_porte else ()},
            {"id": 3, "vis": "admecRuststalker", "team": 1, "pos": (2, 0), "kit": ()}]


FILL, HPMAX = 400, 5000


def test_le_terme_DOUBLE_la_feuille_RepairedAmount_quand_la_cible_porte_le_passif():
    base = repair_utility(FILL, HPMAX, is_boss=False)
    assert base > 0, base                       # TEMOIN NON DEGENERE
    ctx = _CtxDouble(_units(cible_porte=True))
    t = triggered_abilities_non_owner_repair_utility(ctx, 1, 2, FILL, HPMAX)
    assert t == base, (t, base)                 # `Repair(47)` total = base + t = 2 x base


def test_sans_le_passif_sur_la_cible_le_terme_est_nul():
    ctx = _CtxDouble(_units(cible_porte=False))
    assert triggered_abilities_non_owner_repair_utility(ctx, 1, 2, FILL, HPMAX) == 0.0


def test_case_Target_different_de_owner_ne_rend_RIEN():
    """Le porteur est l'unite 2 ; on repare l'unite 3 -> `case.Target != owner` -> yield break."""
    ctx = _CtxDouble(_units(cible_porte=True))
    assert triggered_abilities_non_owner_repair_utility(ctx, 1, 3, FILL, HPMAX) == 0.0


def test_l_exclusion_de_self_est_INCONDITIONNELLE():
    """`<IterateAbilities>d__4` : `if (ta.Owner == subject) continue`, sans garde. Un reparateur
    qui porte lui-meme `VoltagheistField` et se repare ne doit RIEN ajouter."""
    ctx = _CtxDouble(_units(cible_porte=False, caster_porte=True))
    assert triggered_abilities_non_owner_repair_utility(ctx, 1, 1, FILL, HPMAX) == 0.0


def test_le_pre_gate_IsFriend_ecarte_un_porteur_ENNEMI():
    """`<slot 4> = false` -> le pre-gate se reduit a `IsFriend(caster, owner)`."""
    ami = _CtxDouble(_units(cible_porte=True, cible_team=0))
    ennemi = _CtxDouble(_units(cible_porte=True, cible_team=1))
    assert triggered_abilities_non_owner_repair_utility(ami, 1, 2, FILL, HPMAX) > 0
    assert triggered_abilities_non_owner_repair_utility(ennemi, 1, 2, FILL, HPMAX) == 0.0


def test_sans_prediction_le_terme_se_tait():
    ctx = _CtxDouble(_units(cible_porte=True))
    assert triggered_abilities_non_owner_repair_utility(ctx, 1, 2, None, HPMAX) == 0.0
    assert triggered_abilities_non_owner_repair_utility(ctx, 1, 2, FILL, None) == 0.0


def test_le_generateur_d_actions_somme_bien_ce_terme():
    """Le CABLAGE, pas seulement le corps : `_repair_candidates` doit l'appeler. On le verifie par
    le SOURCE du foyer (un test de bout en bout exigerait un runner)."""
    import inspect
    from engine.ai import action_generators as A
    src = inspect.getsource(A.ComparableAbilityGenerator._repair_candidates)
    assert "triggered_abilities_non_owner_repair_utility" in src, src[:400]
