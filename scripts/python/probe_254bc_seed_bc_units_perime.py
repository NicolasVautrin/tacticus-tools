#!/usr/bin/env python
"""#254-bc -- LE BLOC `Units` DU SEED BC N'EST PAS RATTRAPE, et son silence a coute un rouge mal
attribue.

CE QUE CE PROBE MESURE (100 % OFFLINE, aucun runner, aucun RPC) :

  etape 1  ECART -- quelles entrees de `data/seed-bc.json::Units` la synthese depuis le gameconfig
           ne rebatit pas a l'identique, champ par champ.
  etape 2  ATTRIBUTION -- a QUOI cet ecart est du. Le croisement qui l'etablit, avec ses deux
           cellules de contre-exemple.
  etape 3  VACUITE -- la moitie ABILITIES de l'ancien test etait structurellement incapable de
           rougir (elle confrontait la synthese au seed DEJA rafraichi par la synthese).
  etape 4  MUTATIONS -- les gardes de `tests/engine/runner/test_catalog_inject_offline.py`
           rougissent-ils quand on neutralise une moitie de ce qu'ils gardent ?

CONTEXTE. `rl_collect_batch._load_seed_bc` rattrape DEUX des trois catalogues du BC a chaque
chargement -- `BC.Abilities` (#254) et `BC.Utilities` (#27-4). Le TROISIEME, `BC.Units`, ne l'est
pas : c'est lui que `IdunBattle.Core.Services.BattleQuery$$GetUnitConfig` parcourt et dont
`IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` tire les passifs MONTES. Une
entree qui ne correspond pas au gameconfig deploie donc un autre kit, sans erreur ni trace -- et
c'est ce silence, pas l'ecart lui-meme, qui a fait lire l'inertie de `MyWillBeDoneOverlord` comme
un fait du jeu (#354, trois vecteurs de test valides supprimes, restaures par #392).

⚠ L'ACCUSE A CHANGE (#10039), ET C'EST LE POINT DE L'ETAPE 2. Tant que `data/seed-bc.json` etait la
CAPTURE d'une bataille (175 entrees, figee sur `gqfc5mff6c`), l'ecart etait une PEREMPTION
INTER-BUILD, attribuee par les deux tables d'enum versionnees : `MyWillBeDoneOverlord` absente de
l'enum de `gqfc5mff6c`, donc le gameconfig de ce build ne POUVAIT pas l'attribuer. Le fichier est
desormais FORGE par `Idun.Source.IdunBattle.View.BattleConfigBuilder` contre le build COURANT : les
deux cotes viennent du meme build, `necroOverlord` ne diverge plus, et cette attribution-la n'a
plus d'objet. Ce qui reste vient de l'ETAT JOUEUR -- la fabrique enumere l'`IUnitProgression` du
compte, donc une unite non possedee sort a Rank 0 avec ses abilities NON DEBLOQUEES.

    python probe_254bc_seed_bc_units_perime.py            # les 4 etapes
    python probe_254bc_seed_bc_units_perime.py --step 2   # une seule

Code de sortie : 0 si tout est conforme (ecart == epingle, mutations toutes rouges), sinon
le nombre d'anomalies. ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import copy
import json
import sys

import catalog_inject as CI
import gameconfig as G


def _raw_seed() -> dict:
    """Le catalogue BRUT. Passer par `_load_seed_bc` le rafraichirait -- cf. etape 3."""
    return json.loads(CI.SEED_BC.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- etape 1

def step_peremption() -> int:
    seed = _raw_seed()
    n, _diffs = CI.validate(seed)
    stale = CI.stale_unit_entries(seed)
    print("[1] catalogue Units : %d entrees, %d fidele(s) a la synthese, %d avec ecart"
          % (n, n - len(stale), len(stale)))
    for uid in sorted(stale):
        for field, (synth, real) in sorted(stale[uid].items()):
            print("    %-42s %-18s gameconfig=%r" % (uid, field, synth))
            print("    %-42s %-18s catalogue =%r" % ("", "", real))
    attendu = {u: sorted(c) for u, c in CI.STALE_UNIT_ENTRIES.items()}
    obtenu = {u: sorted(c) for u, c in stale.items()}
    ko = 0 if obtenu == attendu else 1
    print("[1] epingle STALE_UNIT_ENTRIES : %s (%d epinglees, %d mesurees)"
          % ("CONFORME" if not ko else "DIVERGE", len(attendu), len(obtenu)))
    if ko:
        print("    NEUVES hors epingle : %r" % sorted(set(obtenu) - set(attendu)))
        print("    epinglees RESORBEES : %r" % sorted(set(attendu) - set(obtenu)))
        for u in sorted(set(obtenu) & set(attendu)):
            if obtenu[u] != attendu[u]:
                print("    CHAMPS %s : epingle=%r mesure=%r" % (u, attendu[u], obtenu[u]))
    return ko


# --------------------------------------------------------------------------- etape 2

def step_attribution() -> int:
    """A QUOI l'ecart est-il du ? Un CROISEMENT, pas une histoire.

    L'attribution INTER-BUILD (qui vivait ici) est close : `data/seed-bc.json` est forge contre le
    build courant, donc les deux cotes du diff viennent du meme build et `necroOverlord` -- son
    unique cas -- ne diverge plus. On le VERIFIE plutot que de le supposer : si l'ancienne derive
    reapparaissait, ce serait un catalogue re-fige sur un vieux build, et il faudrait le relire.
    """
    ko = 0
    seed = _raw_seed()

    # (a) L'ancien accuse : il ne doit plus rien expliquer.
    stale = CI.stale_unit_entries(seed)
    if "necroOverlord" in stale:
        ko += 1
        print("[2] BLOQUANT : `necroOverlord` diverge a nouveau (%r) -- l'attribution INTER-BUILD "
              "redevient la bonne question, relire #254-bc avant d'epingler"
              % sorted(stale["necroOverlord"]))
    gc = G.unit("necroOverlord") or {}
    print("[2] ancien accuse : necroOverlord divergent=%s (gameconfig passiveAbilities=%r)"
          % ("necroOverlord" in stale, gc.get("passiveAbilities")))

    # (b) L'accuse d'aujourd'hui : l'ETAT JOUEUR, etabli par croisement sur les `lineup`.
    tab = CI.player_state_gap(seed)
    vides_div = tab.get((True, True), [])
    pleines_ok = tab.get((False, False), [])
    contre_a = tab.get((True, False), [])
    contre_b = tab.get((False, True), [])
    print("[2] croisement (BC abilities vides) x (divergente) sur les lineup :")
    print("      vide=True  div=True   %4d      vide=True  div=False  %4d  <- contre-exemple"
          % (len(vides_div), len(contre_a)))
    print("      vide=False div=False  %4d      vide=False div=True   %4d  <- contre-exemple"
          % (len(pleines_ok), len(contre_b)))
    if contre_a or contre_b:
        ko += 1
        print("[2] BLOQUANT : une cellule de contre-exemple est NON VIDE -- l'ecart n'est pas "
              "(seulement) l'etat joueur : %r / %r" % (contre_a[:5], contre_b[:5]))
    if not vides_div or not pleines_ok:
        ko += 1
        print("[2] BLOQUANT : croisement DEGENERE (une cellule pleine est vide) -- il ne prouve "
              "rien")

    # (c) La synthese n'invente pas : le gameconfig porte bien le kit qui manque au catalogue.
    sans_kit = [u for u in vides_div
                if not ((G.unit(u.split(":")[0]) or {}).get("activeAbilities")
                        or (G.unit(u.split(":")[0]) or {}).get("passiveAbilities"))]
    if sans_kit:
        ko += 1
        print("[2] BLOQUANT : %r n'ont AUCUN kit au gameconfig -- ce n'est alors pas de l'etat "
              "joueur" % sans_kit[:5])

    # (d) Le RANG ne suffirait pas comme critere : on le MESURE, pour que personne ne s'y fie.
    lineup = set(G._index()["lineup"])
    rank0 = [u["Id"] for u in seed["Units"]
             if u["Id"].split(":")[0] in lineup and int(u.get("Rank") or 0) == 0]
    print("[2] critere REFUTE : %d entrees lineup sont a Rank 0, dont %d seulement divergent "
          "(ex. non divergente : %r)"
          % (len(rank0), len([u for u in rank0 if u in stale]),
             next((u for u in rank0 if u not in stale), None)))
    print("[2] verdict : l'ecart est l'ETAT JOUEUR (abilities non debloquees), 0 contre-exemple")
    return ko


# --------------------------------------------------------------------------- etape 3

def step_vacuite() -> int:
    """L'ancien test comparait la synthese au seed RECHARGE. Le rattrapage venant d'y ecrire le
    resultat de cette meme synthese, l'assertion ne pouvait pas echouer."""
    import rl_collect_batch as R
    raw = _raw_seed()
    nc_raw, _ni, d_raw = CI.validate_abilities(raw)
    derivees = sorted({n for rows in d_raw.values() for n, _s, _r in rows})
    loaded = R._load_seed_bc()
    nc_l, _ni2, d_loaded = CI.validate_abilities(loaded)
    print("[3] validate_abilities sur le catalogue BRUT    : %d confrontees, %d champ(s) divergent"
          " -- abilities=%r" % (nc_raw, len(d_raw), derivees))
    print("[3] validate_abilities sur le seed RECHARGE     : %d confrontees, %d champ(s) divergent"
          % (nc_l, len(d_loaded)))
    if not derivees:
        # ⚠ Depuis #10039 le catalogue est FORGE contre le gameconfig courant : il ne DERIVE plus
        # du tout. La vacuite ne se demontre donc plus par ce substrat -- et c'est precisement ce
        # qui a rendu VACUEUX le test qui s'appuyait dessus (`rattrapage INERTE` passait VERT). Le
        # test FABRIQUE desormais sa derive ; ici on se contente de DIRE que le substrat ne
        # discrimine plus, jamais de rendre un verdict qu'on ne peut pas etablir.
        print("[3] verdict : NON ETABLISSABLE par ce substrat -- le catalogue ne derive plus (0 "
              "config). Toute garde qui s'appuierait sur cette derive est VACUEUSE : la FABRIQUER "
              "(cf. `test_le_rattrapage_repare_exactement_les_configs_dability_qui_derivent`)")
    else:
        print("[3] verdict : l'ancienne assertion `assert not adiffs` sur le seed recharge etait %s"
              % ("VACUEUSE (elle ne pouvait pas rougir)" if not d_loaded
                 else "non concluante ici"))
    # Le bloc Units, LUI, traverse le chargement intact : c'est l'asymetrie qui rendait l'autre
    # moitie du meme test rouge.
    a, b = sorted(CI.stale_unit_entries(raw)), sorted(CI.stale_unit_entries(loaded))
    print("[3] bloc Units : %d entrees avec ecart avant chargement, %d apres -- identiques=%s "
          "(NON rattrape)" % (len(a), len(b), a == b))
    return 0


# --------------------------------------------------------------------------- etape 4

def step_mutations() -> int:
    """Chaque garde du fichier offline doit ROUGIR quand on neutralise une moitie de son objet."""
    import tests.engine.runner.test_catalog_inject_offline as T

    save = {"pin": CI.STALE_UNIT_ENTRIES, "traits": CI._traits,
            "refresh": CI.refresh_ability_configs, "raw": T._raw_seed,
            "gap_lineup": CI.MISSING_LINEUP_ENTRIES, "gap_npc": CI.MISSING_NPC_ENTRIES,
            "rapport": CI.stale_unit_report}

    def restore():
        CI.STALE_UNIT_ENTRIES = save["pin"]
        CI._traits = save["traits"]
        CI.refresh_ability_configs = save["refresh"]
        CI.MISSING_LINEUP_ENTRIES = save["gap_lineup"]
        CI.MISSING_NPC_ENTRIES = save["gap_npc"]
        CI.stale_unit_report = save["rapport"]
        T._raw_seed = save["raw"]

    def _une_epinglee_ab() -> str:
        return sorted(u for u, ch in save["pin"].items()
                      if set(ch) & {"ActiveAbilities", "PassiveAbilities"})[0]

    def raw_kit_rendu():
        """Une entree epinglee retrouve son kit -> elle sort de la cellule (vide, divergente)."""
        bc = save["raw"]()
        uid = _une_epinglee_ab()
        gc = G.unit(uid) or {}
        routed = CI.route_configured_abilities(gc)
        for u in bc["Units"]:
            if u.get("Id") == uid:
                u["ActiveAbilities"] = routed["ActiveAbilities"]
                u["PassiveAbilities"] = routed["PassiveAbilities"]
        return bc

    def raw_divergente_non_vide():
        """Une entree CONCORDANTE recoit un kit FAUX mais NON VIDE -> cellule (False, True)."""
        bc = save["raw"]()
        lineup = set(G._index()["lineup"])
        for u in bc["Units"]:
            if (u["Id"].split(":")[0] in lineup and u["Id"] not in save["pin"]
                    and (u.get("ActiveAbilities") or u.get("PassiveAbilities"))):
                u["ActiveAbilities"] = [999999]
                break
        return bc

    def raw_sans_ecart():
        """Aucune entree ne diverge -> `stale_unit_report` se TAIT, et l'asymetrie n'est plus dite."""
        bc = save["raw"]()
        bc["Units"] = [u for u in bc["Units"] if u.get("Id") not in save["pin"]]
        return bc

    vrai_traits = save["traits"]
    fidelite = T.test_la_synthese_reproduit_le_catalogue_capture_hors_derive_epinglee
    epingle = T.test_le_bloc_units_perime_est_exactement_celui_qui_est_epingle
    attribution = T.test_la_derive_du_bloc_units_est_attribuee_a_l_etat_joueur
    asymetrie = T.test_le_chargement_rafraichit_abilities_et_utilities_mais_PAS_units
    abilities = T.test_le_rattrapage_repare_exactement_les_configs_dability_qui_derivent
    gap_lineup = T.test_l_ecart_d_ajout_lineup_est_exactement_celui_qui_est_epingle
    gap_npc = T.test_l_ecart_d_ajout_npc_est_exactement_celui_qui_est_epingle
    rapport_gap = T.test_le_rapport_d_ecart_se_TAIT_en_regime_nominal_et_PARLE_dans_les_deux_sens

    def pin_vide():
        CI.STALE_UNIT_ENTRIES = {}

    def pin_orpheline():
        CI.STALE_UNIT_ENTRIES = dict(save["pin"], ultraTitus=("Traits",))

    def synthese_amputee():
        CI._traits = lambda gc: vrai_traits(gc)[:-1]

    def rattrapage_inerte():
        CI.refresh_ability_configs = lambda bc, skip=(), withhold=(): ([], [])

    def kit_rendu():
        T._raw_seed = raw_kit_rendu

    def divergente_non_vide():
        T._raw_seed = raw_divergente_non_vide

    def sans_ecart():
        T._raw_seed = raw_sans_ecart

    def rapport_muet():
        CI.stale_unit_report = lambda bc: None

    def epingle_npc_vide():
        CI.MISSING_NPC_ENTRIES = frozenset()

    def epingle_lineup_orpheline():
        CI.MISSING_LINEUP_ENTRIES = frozenset({"zzPasUnHeros"})

    cas = [
        ("epingle VIDE            -> fidelite", pin_vide, fidelite),
        ("epingle VIDE            -> epingle", pin_vide, epingle),
        ("epingle VIDE            -> asymetrie", pin_vide, asymetrie),
        ("epingle ORPHELINE       -> epingle", pin_orpheline, epingle),
        ("synthese AMPUTEE        -> fidelite", synthese_amputee, fidelite),
        ("kit RENDU a une epinglee -> attribution", kit_rendu, attribution),
        ("divergente a kit NON VIDE -> attribution", divergente_non_vide, attribution),
        ("rattrapage INERTE       -> abilities", rattrapage_inerte, abilities),
        ("catalogue SANS ECART    -> asymetrie", sans_ecart, asymetrie),
        ("rapport MUET            -> asymetrie", rapport_muet, asymetrie),
        ("epingle npc VIDE        -> gap npc", epingle_npc_vide, gap_npc),
        ("epingle npc VIDE        -> rapport", epingle_npc_vide, rapport_gap),
        ("epingle lineup ORPHELINE -> gap lineup", epingle_lineup_orpheline, gap_lineup),
        ("epingle lineup ORPHELINE -> rapport", epingle_lineup_orpheline, rapport_gap),
    ]
    ko = 0
    for nom, mutation, test in cas:
        restore()
        mutation()
        try:
            test()
        except AssertionError as e:
            # ⚠ `str(e)` peut etre VIDE (`assert x is None` sans message) : `splitlines()[0]`
            # levait alors IndexError et faisait passer un ROUGE pour un plantage du probe.
            lignes = str(e).splitlines() or ["<assertion sans message>"]
            etat, detail = "ROUGE", lignes[0][:80]
        except Exception as e:                     # pragma: no cover - diagnostic
            etat, detail = "ROUGE(exc)", "%s: %s" % (type(e).__name__, str(e)[:70])
        else:
            etat, detail = "VERT -- NE MORD PAS", ""
            ko += 1
        print("[4] %-42s %-20s %s" % (nom, etat, detail))
    restore()
    for nom in sorted(n for n in dir(T) if n.startswith("test_")):
        try:
            getattr(T, nom)()
        except Exception as e:                     # pragma: no cover - diagnostic
            ko += 1
            print("[4] CONTROLE sans mutation : %s ROUGE INATTENDU -- %s" % (nom, e))
    print("[4] controle sans mutation : les gardes passent")
    return ko


STEPS = {"1": step_peremption, "2": step_attribution, "3": step_vacuite, "4": step_mutations}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--step", default="all", choices=["all"] + sorted(STEPS))
    a = ap.parse_args(argv)
    noms = sorted(STEPS) if a.step == "all" else [a.step]
    ko = 0
    for n in noms:
        ko += STEPS[n]()
        print("")
    print("VERDICT: %s (%d anomalie(s))" % ("PASS" if ko == 0 else "FAIL", ko))
    return ko


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
