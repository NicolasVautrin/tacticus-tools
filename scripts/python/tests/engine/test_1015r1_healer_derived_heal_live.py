"""#1015-r1 -- CONFRONTATION LIVE du canal trait `Healer` -> ability active `18 Heal`.

CRITERE BINAIRE : le kit d'abilities que le PORT reconstruit (`state_bridge.build_from_state`, qui
passe par `_abilities_of` + `entities.active_abilities.derived_active_ability_ids`) porte-t-il la
MEME ability `18 Heal` que celle que le NATIF publie (`decisionView` / `abilityTargets`, `kind ==
"granted"`) ?

CE QUE LE NATIF FAIT, et qu'on confronte ici (chaine lue au decompile, cf. le cliquet OFFLINE
jumeau `test_1015r1_healer_derived_heal_offline.py`) : `Trait$$GetActiveAbility` mappe
`UnitTrait.Healer(0x0a)` -> `ActiveAbilityType.Heal(0x12)`, et
`IdunBattle.Entities.Factories.UnitFactory$$AddDerivedAbilities` la pousse dans
l'`ActiveAbilityComponent` au niveau 1. L'ability n'est dans AUCUN `activeAbilities` gameconfig :
le trait est sa SEULE source.

QUATRE REGIMES, et le TEMOIN NON-NUL est le couple (2, 3) -- la MEME unite, deux etats de traits,
deux comportements natifs differents :

  1. `adeptHospitaller`  porteur NATIF de `Healer`                 -> 18 des DEUX cotes
  2. `ultraTigurius`     NON porteur                               -> 18 d'AUCUN cote
  3. `ultraTigurius`     avec `--unit-stat 'Traits=[...,"Healer"]'`-> 18 des DEUX cotes  <-- GREFFE
  4. `genesBiophagus`    `Healer` + passif `TwistedScience`        -> 1167 seule, 18 RETIREE

Le regime 4 confronte l'autre moitie du port : le `RemoveActiveAbility(Owner, 0x12)` que
`TwistedScienceAbility$$CreateBehaviour` execute a l'init.

MESURE DE MONTAGE (#1015-r1, meme resultat que la tranche soeur `CloseCombatWeakness`) : AUCUNE
injection de config de trait n'est requise -- `--unit-stat "<vis>:Traits=[...]"` suffit, le natif
monte la derivee tout seul. Ce n'est pas le verrou d'une relique (#237).

ASCII only. Dispose SES runners (fabrique `build_runner`).
"""
from __future__ import annotations

import pytest

from engine.ai.state_bridge import build_from_state
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.pathfinding.board import Board
from engine.entities.traits.unit_trait import UnitTrait, entity_trait_names
from engine.runner.components import StatsComponent, UnitComponent
from engine.runner.snapshot import load_state

#: Ce qui doit faire REJOUER ce fichier.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/active_abilities.py",
        "scripts/python/engine/entities/active_ability_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/ai/state_bridge.py",
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/rl_duel.py",
    ),
    "build": True,
    "toujours": False,
    "raison": (
        "Confrontation LIVE de #1015-r1 : le kit reconstruit par le port contre celui que le natif "
        "publie, sur quatre regimes dont une GREFFE de trait. Depend du build (le dict "
        "`Trait$$GetActiveAbility` est dans le binaire) et de deux runners."),
}

HEAL = int(ActiveAbilityType.Heal)                       # 0x12 = 18
TWISTED = int(ActiveAbilityType.Heal_TwistedScience)     # 0x48f = 1167
TRAIT = UnitTrait.Healer.name

P_NATURE = "adeptHospitaller,ultraTigurius,genesBiophagus"
P_GREFFE = "ultraTigurius,adeptHospitaller"
TRAITS_GREFFES = '["Hero","Psyker","%s"]' % TRAIT        # `ultraTigurius` = Hero + Psyker au kit


def _charge(rpc, rid):
    """(state, natif) -- `natif[vid] = set(ids d'abilities publiees)`, tous kinds confondus.

    Le kind n'est PAS filtre a dessein : `18` sort en `granted` (elle vient d'`AddDerivedAbilities`)
    et une regression qui la ferait passer en `active` resterait une reussite du canal. Ce qu'on
    confronte est la PRESENCE, cote natif comme cote port."""
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 180)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    cs = rpc("combatSnapshot", {"runnerId": rid}, 60)
    natif = {}
    for u in (dv.get("units") or []):
        vis = u.get("visualId")
        if not vis:
            continue
        natif[vis] = {int(a["id"]) for a in (u.get("abilities") or []) if a.get("id") is not None}
    return load_state(dv, ob, cs, board=board), natif


def _uid(state, vis):
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.visual_id == vis:
            return eid
    return None


def _porte(state, vis) -> set:
    """Ids d'abilities que le PORT publie pour cette unite (`ctx.me["abilities"]`)."""
    uid = _uid(state, vis)
    assert uid is not None, "unite %r absente du State" % vis
    d = build_from_state(state, uid)
    return {int(a["id"]) for a in ((d.me or {}).get("abilities") or [])}


@pytest.fixture(scope="module")
def nature(rpc, build_runner):
    """Bataille LIVE aux traits NATURELS : porteur, non-porteur et porteur-qui-substitue."""
    rid = build_runner("777", board="MC1_67", extra=["--p-units", P_NATURE])["rid"]
    return _charge(rpc, rid)


@pytest.fixture(scope="module")
def greffe(rpc, build_runner):
    """MEME board, MEME seed -- seul `Traits` d'`ultraTigurius` change. C'est le contre-bras."""
    rid = build_runner("777", board="MC1_67",
                       extra=["--p-units", P_GREFFE,
                              "--unit-stat", "ultraTigurius:Traits=%s" % TRAITS_GREFFES])["rid"]
    return _charge(rpc, rid)


# ================================================================================================
# 0. LE MONTAGE MESURE CE QU'IL CROIT
# ================================================================================================

def test_le_montage_est_discriminant(nature, greffe):
    """Verrou anti-tautologie, dans les DEUX sens :
      * la greffe a MORDU (`ultraTigurius` porte `Healer` en bataille, pas au kit) ;
      * le regime nature ne le porte PAS (sinon les deux bras seraient le meme).
    Sans cet etage, un `--unit-stat` silencieusement ignore rendrait les tests suivants verts par
    accord dans un regime DEGENERE."""
    st_n, _ = nature
    st_g, _ = greffe
    uid_n, uid_g = _uid(st_n, "ultraTigurius"), _uid(st_g, "ultraTigurius")
    assert uid_n is not None and uid_g is not None, "ultraTigurius absent d'un des deux runners"
    tr_n = entity_trait_names(getattr(st_n.get_entity(uid_n).get_component(StatsComponent),
                                      "ctx", None), "ultraTigurius")
    tr_g = entity_trait_names(getattr(st_g.get_entity(uid_g).get_component(StatsComponent),
                                      "ctx", None), "ultraTigurius")
    assert TRAIT not in tr_n, ("le bras NATURE porte deja `%s` : les deux bras sont le meme "
                               "regime, l'accord ne prouverait rien. Traits : %r" % (TRAIT, tr_n))
    assert TRAIT in tr_g, ("`--unit-stat Traits` n'a PAS mordu : la greffe est inerte et le "
                           "temoin non-nul n'existe pas. Traits : %r" % (tr_g,))


# ================================================================================================
# 1-2. PORTEUR NATIF vs NON-PORTEUR -- le natif d'abord, le port ensuite
# ================================================================================================

def test_le_natif_donne_18_au_porteur_et_rien_au_non_porteur(nature):
    """LA MESURE, avant toute comparaison avec le port. `adeptHospitaller` n'a `Heal` dans AUCUN
    `activeAbilities` gameconfig : si le natif la publie, elle vient du TRAIT."""
    _st, natif = nature
    assert "adeptHospitaller" in natif and "ultraTigurius" in natif, sorted(natif)
    assert HEAL in natif["adeptHospitaller"], (
        "le natif ne publie PAS `18 Heal` pour un porteur `%s` -- la premisse du port est fausse, "
        "RE-LIRE `Trait$$GetActiveAbility` avant de toucher au port. Publie : %r"
        % (TRAIT, sorted(natif["adeptHospitaller"])))
    assert HEAL not in natif["ultraTigurius"], (
        "le natif publie `18 Heal` pour une unite SANS le trait : la source n'est pas le trait. "
        "Publie : %r" % sorted(natif["ultraTigurius"]))


@pytest.mark.parametrize("vis,attendu", [("adeptHospitaller", True), ("ultraTigurius", False)])
def test_le_port_reconstruit_le_meme_verdict_que_le_natif(nature, vis, attendu):
    st, natif = nature
    assert (HEAL in natif[vis]) is attendu, "premisse cassee cote NATIF pour %s" % vis
    assert (HEAL in _porte(st, vis)) is attendu, (
        "%s : le port %s `18 Heal` alors que le natif %s. Port : %r / natif : %r"
        % (vis, "donne" if attendu else "ne donne pas", "la donne" if attendu else "ne la donne pas",
           sorted(_porte(st, vis)), sorted(natif[vis])))


# ================================================================================================
# 3. LA GREFFE -- le temoin NON NUL
# ================================================================================================

def test_la_greffe_donne_18_au_natif_ET_au_port(greffe):
    """La MEME unite qui n'avait rien au bras NATURE recoit `18 Heal` des deux cotes une fois
    `Healer` pose. C'est ce couple, et lui seul, qui etablit que le canal porte est bien le TRAIT
    et non le `visualId`."""
    st, natif = greffe
    assert HEAL in natif["ultraTigurius"], (
        "le natif ne derive PAS `18 Heal` d'un trait `%s` accorde par `--unit-stat` : soit le "
        "montage n'a pas mordu (cf. l'etage 0), soit `AddDerivedAbilities` ne lit pas ce substrat. "
        "Publie : %r" % (TRAIT, sorted(natif["ultraTigurius"])))
    assert HEAL in _porte(st, "ultraTigurius"), (
        "le port ne suit pas la greffe : `entity_trait_names` -> `derived_active_ability_ids` n'a "
        "pas mordu. Port : %r" % sorted(_porte(st, "ultraTigurius")))


# ================================================================================================
# 4. LE RETRAIT PAR LE PASSIF SUBSTITUTIF
# ================================================================================================

def test_le_porteur_qui_substitue_perd_18_au_natif_ET_au_port(nature):
    """`genesBiophagus` porte `Healer` ET le passif `TwistedScience`, dont le `CreateBehaviour` fait
    `RemoveActiveAbility(Owner, 0x12) & AddActiveAbility(Owner, 0x48f, state)`. Le natif ne lui
    laisse donc que `1167`, et le port doit faire de meme -- sans ce retrait, le decideur offline
    lui proposerait DEUX soins la ou le natif n'en offre qu'un."""
    st, natif = nature
    assert "genesBiophagus" in natif, sorted(natif)
    assert TWISTED in natif["genesBiophagus"], (
        "`1167 Heal_TwistedScience` absente cote natif : la premisse du regime 4 est cassee (%r)"
        % sorted(natif["genesBiophagus"]))
    assert HEAL not in natif["genesBiophagus"], (
        "le natif laisse `18` ET `1167` : le `RemoveActiveAbility` n'a pas eu lieu, RE-LIRE "
        "`TwistedScienceAbility$$CreateBehaviour` (%r)" % sorted(natif["genesBiophagus"]))
    porte = _porte(st, "genesBiophagus")
    assert TWISTED in porte, "le port perd `1167` : regression de `_granted_abilities` (%r)" % sorted(porte)
    assert HEAL not in porte, (
        "le port donne `18` a un porteur qui SUBSTITUE : `PASSIVE_REMOVES_ACTIVE_ABILITY` n'est pas "
        "applique, ou son substrat de passifs est muet. Port : %r" % sorted(porte))
