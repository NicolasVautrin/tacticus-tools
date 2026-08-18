"""#488-r3 -- CLIQUET : les MODS ATTAQUANT du canal #179 sont evalues au profil DU GROUPE.

LE GISEMENT, ETABLI PAR #488-r2 ET MESURE
------------------------------------------
Cote NATIF, un groupe additionnel a profil PROPRE est une SOUS-OPERATION entiere
(`IdunBattle.Operations.ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute` -> slot 0x3c
-> `IdunBattle.Operations.AttackDamageOperation$$Execute`) : son
`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` rebatit un
`IdunBattle.Entities.Abilities.AbilityEntities` NEUF dont le `DamageProfile` est celui DU GROUPE,
et c'est cet objet que `IdunBattle.Core.Services.DamageCalculations$$
CalculateAttackerModifiersForPrediction` passe a chaque effet.

Cote PORT, `execute_additional_hits` recevait `mods` en ARGUMENT (resolus une fois par la phase
d'ARME) et le reutilisait pour tous les groupes -- alors qu'il threadait deja `g_profile` dans
TROIS autres canaux du groupe. Consequence MESUREE (`probe_488r2_profil_du_groupe.py` etape 3) :
sur `blackObliterator` (arme `HeavyRound`, cycle `FleshmetalGuns` au profil `Melta`),
`MeltaExtraDmgEffect` rend `None` a `HeavyRound` et `+50 %` a `Melta` -> le bonus vs `Vehicle`
etait INERTE sur les coups du groupe.

CE QUE CE FICHIER GARDE, ET POURQUOI EN CINQ ETAGES SEPARES
------------------------------------------------------------
La reparation devait SEPARER DEUX FAMILLES : les bonus gates par profil (a reevaluer) et ceux qui
ne le sont pas (a PARTAGER -- la docstring d'`execute_additional_hits` porte une mesure LIVE
`2468 s14` qui valide le partage pour `CrushingStrike`). Un seul test « le degat monte » ne
distinguerait pas les deux ; il passerait aussi pour une re-collecte EN BLOC, que la fiche
interdit. D'ou :

  E1 CANAL MUET        -- sans re-collecteur, tout est STRICTEMENT comme avant (bit-a-bit).
  E2 SUBSTITUTION      -- quand le profil du groupe CHANGE les mods, ils sont remplaces.
  E3 NON-SUBSTITUTION  -- quand il ne les change PAS, l'objet de la phase d'arme est GARDE.
                          C'est l'etage qui protege la mesure live `2468 s14`.
  E4 PROFIL HERITE     -- un groupe sans profil propre emprunte celui de l'arme : jamais substitue.
  E5 CONSOMMATION RNG  -- identique dans les trois regimes (le bloc ne tire pas).
  E6 CABLAGE           -- les appelants de `execute_additional_hits` passent le re-collecteur.
  E7 FOYER             -- `attacker_modifiers_at_profile` propage bien le profil jusqu'a l'effet.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_PY = Path(__file__).resolve().parents[3]
if str(_PY) not in sys.path:
    sys.path.insert(0, str(_PY))

import gameconfig as GC                                                       # noqa: E402
from engine.entities.unit_context import UnitContext                          # noqa: E402
from engine.runner.components import (HealthComponent, OwnerComponent,        # noqa: E402
                                      PositionComponent, StatsComponent, UnitComponent)
from engine.runner.operations.additional_hits import execute_additional_hits  # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister                        # noqa: E402
from engine.runner.state import State                                         # noqa: E402
from engine.services.damage_modifiers import DamageModifiers, add_modifier    # noqa: E402
from engine.entities.effects.base import EffectBonus                          # noqa: E402

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # E1..E5 traversent le foyer du canal #179, le pipeline de degat, les mods et le PRNG ;
        # E6 balaye l'AST de tout `engine/**` pour trouver les appelants ; E7 va jusqu'a l'effet.
        # Declarer les seuls modules de `damage_ops/` serait DECLARER TROP ETROIT, et un
        # declencheur trop etroit est un FAUX VERT.
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
        "scripts/python/gameconfig.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Cinq etages OFFLINE : montage `State` en memoire, aucun runner, aucune session, "
              "aucun RPC. E1..E5 executent le canal #179 (`execute_additional_hits`) avec un "
              "re-collecteur SYNTHETIQUE -- le montage ne depend donc d'aucun porteur ni d'aucun "
              "seed BC. E6 lit l'AST d'`engine/**` (les appelants sont DERIVES, jamais listes). "
              "E7 lit le gameconfig (`meltaDamageExtraDmgPct`) et l'effet porte.",
}

MELTA = "Melta"
ARME = "HeavyRound"


def _etat():
    """Attaquant + cible, montage minimal. Meme forme que `probe_488r2_profil_du_groupe._etat`."""
    st = State()
    st.rng = IntBasedMersenneTwister(4463111)
    ids = []
    for i, vis in enumerate(("blackObliterator", "admecDestroyer")):
        e = st.add_entity()
        e.add_component(UnitComponent(visual_id=vis, alive=True))
        e.add_component(HealthComponent(hp=400000, hp_max=400000))
        e.add_component(OwnerComponent(team=i, player=i))
        e.add_component(PositionComponent(i * 4, 0))
        e.add_component(StatsComponent(ctx=UnitContext(entity_id=e.id, visual_id=vis)))
        ids.append(e.id)
    return st, ids[0], ids[1]


def _mods_avec_bonus(pct: int) -> DamageModifiers:
    """Des mods attaquant portant UN `PercentIncrease` -- la forme exacte que rend
    `MeltaExtraDmgEffect.create_effect_damage_bonus_for_attack` quand son gate passe."""
    m = DamageModifiers()
    if pct:
        add_modifier(m, EffectBonus(kind="PercentIncrease", value=pct, owner_is_caster=True))
    return m


def _joue(recollecteur, groupes, mods_arme=None, seed: int = 4463111):
    """Un passage du canal #179, RNG neuve a chaque appel -> deux passages sont comparables."""
    st, att, tgt = _etat()
    st.rng = IntBasedMersenneTwister(seed)
    e_t = st.get_entity(tgt)
    thc = e_t.get_component(HealthComponent)
    out = execute_additional_hits(
        st, att, tgt, e_t, thc, groupes,
        mods_arme if mods_arme is not None else DamageModifiers(), DamageModifiers(),
        0, 1, None, None,
        attack_profile=ARME,
        attacker_mods_for_profile=recollecteur)
    return out, st.rng


def _groupe(profil, count=2, mn=1000, mx=1000):
    return {"profile": profil, "count": count, "min": mn, "max": mx}


# --------------------------------------------------------------------------------------------- #
# E1 -- CANAL MUET : sans re-collecteur, rien ne bouge
# --------------------------------------------------------------------------------------------- #
def test_e1_canal_muet_strictement_inchange():
    """`attacker_mods_for_profile=None` est le comportement d'AVANT #488-r3, et il doit le rester
    BIT A BIT : tout appelant non cable (probes, tests, vecteurs tiers) passe par la.

    Le TEMOIN est un re-collecteur qui rend TOUJOURS les memes mods : les deux collectes de la
    double lecture sont alors egales, donc la substitution ne se declenche pas -- et le resultat
    doit egaler celui du canal muet."""
    grp = [_groupe(MELTA)]
    muet, _ = _joue(None, grp)
    constant, _ = _joue(lambda _p: DamageModifiers(), grp)
    assert muet["total"] > 0, ("le montage n'inflige aucun degat : ce fichier ne prouverait rien "
                               "(un zero de montage n'est pas une mesure)")
    assert muet["per_hit"] == constant["per_hit"], (
        "un re-collecteur CONSTANT change le resultat : la substitution se declenche alors "
        "qu'aucun mod ne depend du profil -- muet=%s constant=%s"
        % (muet["per_hit"], constant["per_hit"]))
    assert muet["profile_mods_substitues"] == 0
    assert constant["profile_mods_substitues"] == 0


# --------------------------------------------------------------------------------------------- #
# E2 -- SUBSTITUTION : le profil du groupe change les mods -> ils sont remplaces
# --------------------------------------------------------------------------------------------- #
def test_e2_le_profil_du_groupe_substitue_les_mods_attaquant():
    """Le cas `blackObliterator` : arme `HeavyRound`, groupe `Melta`, bonus +50 % qui n'existe QUE
    pour `Melta`. Avant #488-r3 le gate etait evalue avec `HeavyRound` -> bonus INERTE."""
    grp = [_groupe(MELTA)]
    sans, _ = _joue(None, grp)
    avec, _ = _joue(lambda p: _mods_avec_bonus(50 if p == MELTA else 0), grp)
    assert avec["profile_mods_substitues"] == 1, (
        "le groupe `Melta` n'a PAS vu ses mods re-collectes (substitues=%s) : le canal est "
        "inerte" % avec["profile_mods_substitues"])
    assert avec["total"] > sans["total"], (
        "le +50 %% `Melta` ne mord pas sur les coups du groupe : sans=%s avec=%s"
        % (sans["total"], avec["total"]))


# --------------------------------------------------------------------------------------------- #
# E3 -- NON-SUBSTITUTION : le profil ne change rien -> l'objet de l'arme est GARDE
# --------------------------------------------------------------------------------------------- #
def test_e3_un_bonus_non_gate_par_profil_reste_celui_de_la_phase_d_arme():
    """L'ETAGE QUI PROTEGE LA MESURE LIVE `2468 s14` (`ExplosiveMaladies` subit le x1.5
    `CrushingStrike` de la phase d'arme). Un bonus qui ne depend PAS du profil rend les deux
    collectes EGALES -> aucune substitution, et le `mods` de l'arme continue de s'appliquer.

    ⚠ Le contre-temoin est dans l'assertion : si le port re-collectait EN BLOC, `mods_arme`
    serait REMPLACE par la collecte du groupe (qui, ici, ne porte PAS le bonus d'arme) et le
    degat CHUTERAIT. C'est exactement la faute que la fiche du residu interdit."""
    grp = [_groupe(MELTA)]
    mods_arme = _mods_avec_bonus(50)          # le x1.5 de la phase d'arme, non gate par profil
    # le re-collecteur ne connait PAS ce bonus (il modelise un effet insensible au profil, donc
    # identique pour les deux profils) -> les deux collectes sont egales.
    ref, _ = _joue(None, grp, mods_arme=mods_arme)
    mesure, _ = _joue(lambda _p: DamageModifiers(), grp, mods_arme=mods_arme)
    assert mesure["profile_mods_substitues"] == 0, (
        "substitution declenchee alors que le profil ne change AUCUN mod -- une re-collecte EN "
        "BLOC ecraserait le bonus de la phase d'arme")
    assert mesure["per_hit"] == ref["per_hit"], (
        "le bonus d'arme non gate par profil a ete perdu : ref=%s mesure=%s"
        % (ref["per_hit"], mesure["per_hit"]))


# --------------------------------------------------------------------------------------------- #
# E4 -- PROFIL HERITE : un groupe sans profil propre n'est jamais substitue
# --------------------------------------------------------------------------------------------- #
def test_e4_un_groupe_qui_herite_du_profil_de_l_arme_n_est_jamais_substitue():
    """`g_profile is None` -> le groupe emprunte le profil de l'ATTAQUE (c'est ce que fait
    `ExecuteHits` quand le `Nullable` du groupe n'a pas de valeur). Il n'y a donc AUCUN changement
    de profil, donc aucune raison de re-collecter -- et le re-collecteur n'est meme pas appele."""
    appels: list = []

    def _rec(p):
        appels.append(p)
        return _mods_avec_bonus(999)          # absurde : s'il etait pris, le degat exploserait

    grp = [_groupe(None)]
    ref, _ = _joue(None, grp)
    mesure, _ = _joue(_rec, grp)
    assert appels == [], ("le re-collecteur a ete appele pour un groupe SANS profil propre : %s"
                          % appels)
    assert mesure["profile_mods_substitues"] == 0
    assert mesure["per_hit"] == ref["per_hit"]


# --------------------------------------------------------------------------------------------- #
# E5 -- CONSOMMATION RNG : le bloc ne tire pas
# --------------------------------------------------------------------------------------------- #
def test_e5_la_consommation_rng_est_identique_dans_les_trois_regimes():
    """`attacker_modifiers` est une LECTURE (effets, positions) : re-collecter ne doit consommer
    AUCUN tirage. Si ce n'etait pas vrai, la substitution desynchroniserait le flux de toute
    l'attaque -- exactement le risque que la fiche du residu signale."""
    grp = [_groupe(MELTA), _groupe(None)]
    n = []
    for rec in (None, lambda _p: DamageModifiers(),
                lambda p: _mods_avec_bonus(50 if p == MELTA else 0)):
        out, rng = _joue(rec, grp)
        n.append(len(out["rolls"]))
    assert len(set(n)) == 1, ("la consommation RNG bouge selon le regime de mods : %s "
                              "(muet / constant / gate-profil)" % n)
    assert n[0] > 0, "aucun tirage : le montage ne traverse pas la boucle de coups"


# --------------------------------------------------------------------------------------------- #
# E6 -- CABLAGE : les appelants passent le re-collecteur
# --------------------------------------------------------------------------------------------- #
def test_e6_les_appelants_de_execute_additional_hits_cablent_le_recollecteur():
    """DERIVE : on cherche les appels a `execute_additional_hits` dans tout `engine/**` (AST) et on
    exige que chacun passe `attacker_mods_for_profile`. Une liste ecrite a la main raterait le
    prochain vecteur qui monterait des groupes.

    ⚠ Le recenseur visite `ast.Attribute` AUTANT que `ast.Name` : un appel ecrit en FORME B
    (`AH.execute_additional_hits(...)`) lui echapperait sinon, et il rendrait `0 appelant` --
    c'est-a-dire un vert sur rien."""
    import ast
    racine = _PY / "engine"
    sites = []
    for p in sorted(racine.rglob("*.py")):
        try:
            arbre = ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        for n in ast.walk(arbre):
            if not isinstance(n, ast.Call):
                continue
            f = n.func
            nom = (f.attr if isinstance(f, ast.Attribute)
                   else (f.id if isinstance(f, ast.Name) else None))
            if nom != "execute_additional_hits":
                continue
            kw = {k.arg for k in n.keywords if k.arg}
            sites.append((p.relative_to(racine).as_posix(), n.lineno,
                          "attacker_mods_for_profile" in kw))
    assert sites, ("aucun appel a `execute_additional_hits` trouve dans engine/** : le recenseur "
                   "ne visite plus rien (un zero de recenseur n'est pas une preuve)")
    muets = [(f, ln) for f, ln, ok in sites if not ok]
    assert not muets, (
        "appel(s) a `execute_additional_hits` SANS `attacker_mods_for_profile` : %s. Les mods "
        "attaquant y resteront evalues au profil de l'ARME sur tous les groupes #179 (#488-r3)."
        % muets)


# --------------------------------------------------------------------------------------------- #
# E7 -- FOYER : `attacker_modifiers_at_profile` propage le profil jusqu'a l'effet
# --------------------------------------------------------------------------------------------- #
def test_e7_le_foyer_partage_propage_le_profil_jusqu_a_l_effet():
    """Le re-collecteur ne vaut que si le profil arrive jusqu'au gate de l'effet. On le verifie a
    la SOURCE, sur le consommateur mesure par #488-r2 -- et on ASSERTIONNE le contre-temoin
    (`HeavyRound` -> rien) : sans lui, un effet devenu inconditionnel passerait pour une reussite.
    """
    from engine.entities.effects.loki.extra_damage import MeltaExtraDmgEffect
    from engine.entities.traits.unit_trait import UnitTrait
    eff = MeltaExtraDmgEffect(1297)
    cibles = frozenset({UnitTrait.Vehicle.name})
    sans = eff.create_effect_damage_bonus_for_attack(
        is_ranged=True, target_traits=cibles, att_ctx={"damage_profile": ARME})
    avec = eff.create_effect_damage_bonus_for_attack(
        is_ranged=True, target_traits=cibles, att_ctx={"damage_profile": MELTA})
    assert sans is None, ("`MeltaExtraDmgEffect` rend un bonus au profil `%s` : le gate "
                          "`DamageProfileHasTrait(OnMelta)` ne discrimine plus, ce test serait "
                          "vacant" % ARME)
    assert avec is not None and int(getattr(avec, "value", 0)) == int(
        GC.global_value("meltaDamageExtraDmgPct") or 0), (
        "bonus `Melta` absent ou d'une autre magnitude que `meltaDamageExtraDmgPct` : %r" % (avec,))


# --------------------------------------------------------------------------------------------- #
# E8 -- LE FOYER : `attacker_modifiers_at_profile` PASSE le profil qu'on lui demande
# --------------------------------------------------------------------------------------------- #
def test_e8_le_foyer_passe_le_profil_demande_a_la_collecte_et_au_trench(monkeypatch):
    """E1..E5 utilisent un re-collecteur SYNTHETIQUE : ils gardent le CABLAGE du canal #179, pas le
    foyer que les appelants lui donnent. Sans cet etage-ci, `attacker_modifiers_at_profile`
    pourrait cesser de propager le profil (le figer a `None`, par exemple) sans qu'un seul test ne
    bouge -- mesure faite : ce mutant-la etait MUET avant cet etage.

    On substitue les TROIS dependances du foyer dans SON module (`damage_model`, qui les lie en
    forme A chez lui : `monkeypatch.setattr` sur le module MORD) et on lit ce qu'elles recoivent.
    Les deux feuilles positionnelles sont verifiees APPELEES, parce que le builder natif les porte
    dans le meme etage et que `calculate_trench_reduction` lit elle aussi le profil."""
    from engine.runner import damage_model as DM
    vus: dict = {"collecte": [], "elevation": 0, "trench": []}

    def _fake_collecte(state, uid, hp, **kw):
        vus["collecte"].append(kw.get("damage_profile"))
        return DamageModifiers(), []

    def _fake_elev(state, mods, a, t):
        vus["elevation"] += 1

    def _fake_trench(state, mods, a, t, damage_profile=None):
        vus["trench"].append(damage_profile)

    monkeypatch.setattr(DM, "attacker_modifiers", _fake_collecte)
    monkeypatch.setattr(DM, "apply_elevation_bonus", _fake_elev)
    monkeypatch.setattr(DM, "apply_trench_reduction", _fake_trench)

    st, att, tgt = _etat()
    for prof in (ARME, MELTA, None):
        DM.attacker_modifiers_at_profile(st, att, 100, tgt, prof, is_ranged=True)

    assert vus["collecte"] == [ARME, MELTA, None], (
        "le profil demande n'arrive pas a la collecte d'effets : %s" % vus["collecte"])
    assert vus["trench"] == [ARME, MELTA, None], (
        "le profil demande n'arrive pas a `apply_trench_reduction`, qui le LIT "
        "(`IgnoreTrenchReduction`) : %s" % vus["trench"])
    assert vus["elevation"] == 3, (
        "`apply_elevation_bonus` n'est pas appelee a chaque collecte : des mods AMPUTES par "
        "rapport a ceux de la phase d'arme feraient accuser l'elevation au lieu du profil "
        "(appels=%d)" % vus["elevation"])


if __name__ == "__main__":                       # pragma: no cover
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-q"]))
