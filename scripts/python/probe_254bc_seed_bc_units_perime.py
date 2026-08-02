#!/usr/bin/env python
"""#254-bc -- LE BLOC `Units` DU SEED BC EST PERIME, et son silence a coute un rouge mal attribue.

CE QUE CE PROBE MESURE (100 % OFFLINE, aucun runner, aucun RPC) :

  etape 1  PEREMPTION -- quelles entrees de `data/seed-bc.json::Units` le gameconfig VIVANT ne
           rebatirait plus a l'identique, champ par champ.
  etape 2  ATTRIBUTION -- pourquoi c'est la CAPTURE qui est en arriere, et non la synthese qui
           invente : les DEUX tables d'enum versionnees et le gameconfig vivant.
  etape 3  VACUITE -- la moitie ABILITIES de l'ancien test etait structurellement incapable de
           rougir (elle confrontait la synthese au seed DEJA rafraichi par la synthese).
  etape 4  MUTATIONS -- les gardes de `tests/engine/runner/test_catalog_inject_offline.py`
           rougissent-ils quand on neutralise une moitie de ce qu'ils gardent ?

CONTEXTE. `rl_collect_batch._load_seed_bc` rattrape DEUX des trois catalogues du BC a chaque
chargement -- `BC.Abilities` (#254) et `BC.Utilities` (#27-4). Le TROISIEME, `BC.Units`, ne l'est
pas : c'est lui que `IdunBattle.Core.Services.BattleQuery$$GetUnitConfig` parcourt et dont
`IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` tire les passifs MONTES. Une
entree perimee deploie donc le kit d'un ANCIEN build, sans erreur ni trace -- et c'est ce silence,
pas la peremption elle-meme, qui a fait lire l'inertie de `MyWillBeDoneOverlord` comme un fait du
jeu (#354, trois vecteurs de test valides supprimes, restaures par #392).

Le rattrapage n'est PAS fait ici : re-dumper le seed change le pool spawnable et les stats de
reference de tous les tests live -- c'est un arbitrage (#254-bc au backlog). Ce probe MESURE et le
test GARDE ; l'arbitrage reste ouvert.

    python probe_254bc_seed_bc_units_perime.py            # les 4 etapes
    python probe_254bc_seed_bc_units_perime.py --step 2   # une seule

Code de sortie : 0 si tout est conforme (peremption == epingle, mutations toutes rouges), sinon
le nombre d'anomalies. ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import copy
import json
import sys

import catalog_inject as CI
import gameconfig as G
import symbols_layout

#: Build sur lequel `data/seed-bc.json` a ete capture (UN seul commit : `f467e649`).
BUILD_CAPTURE = "gqfc5mff6c"


def _raw_seed() -> dict:
    """La capture BRUTE. Passer par `_load_seed_bc` la rafraichirait -- cf. etape 3."""
    return json.loads(CI.SEED_BC.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- etape 1

def step_peremption() -> int:
    seed = _raw_seed()
    n, _diffs = CI.validate(seed)
    stale = CI.stale_unit_entries(seed)
    print("[1] catalogue Units : %d entrees, %d fidele(s) a la synthese, %d perimee(s)"
          % (n, n - len(stale), len(stale)))
    for uid in sorted(stale):
        for field, (synth, real) in sorted(stale[uid].items()):
            print("    %-16s %-18s gameconfig=%r" % (uid, field, synth))
            print("    %-16s %-18s capture   =%r" % ("", "", real))
    attendu = {u: sorted(c) for u, c in CI.STALE_UNIT_ENTRIES.items()}
    obtenu = {u: sorted(c) for u, c in stale.items()}
    ko = 0 if obtenu == attendu else 1
    print("[1] epingle STALE_UNIT_ENTRIES : %s (attendu=%r mesure=%r)"
          % ("CONFORME" if not ko else "DIVERGE", attendu, obtenu))
    return ko


# --------------------------------------------------------------------------- etape 2

def step_attribution() -> int:
    ko = 0
    cur_name = symbols_layout.current_build()
    cur = CI.enum_map("IdunBattle.Entities.Enum.TriggeredAbilityType")
    cur_tr = CI.enum_map("IdunBattle.Entities.Enum.UnitTrait")
    archives = symbols_layout.archived_builds()
    print("[2] builds versionnes : courant=%s archives=%r" % (cur_name, archives))
    if BUILD_CAPTURE not in archives:
        # On DIT qu'on ne mesure pas -- jamais un zero muet (#273).
        print("[2] BLOQUANT : la table du build de la capture (%s) n'est pas archivee, "
              "l'attribution n'est pas re-derivable" % BUILD_CAPTURE)
        return 1
    old = CI.enum_map("IdunBattle.Entities.Enum.TriggeredAbilityType", BUILD_CAPTURE)
    old_tr = CI.enum_map("IdunBattle.Entities.Enum.UnitTrait", BUILD_CAPTURE)
    print("[2] TriggeredAbilityType : %s=%d membres, %s=%d membres"
          % (BUILD_CAPTURE, len(old), cur_name, len(cur)))
    for nom in ("MyWillBeDoneOverlord", "MartialApotheosis"):
        print("      %-22s %s=%s  %s=%s" % (nom, BUILD_CAPTURE, old.get(nom), cur_name,
                                            cur.get(nom)))
    print("      %-22s %s=%s  %s=%s" % ("UnitTrait.Resilient", BUILD_CAPTURE,
                                        old_tr.get("Resilient"), cur_name,
                                        cur_tr.get("Resilient")))
    if "MyWillBeDoneOverlord" in old:
        ko += 1
        print("[2] BLOQUANT : l'ability existait deja sur %s -- la derive n'est plus attribuable "
              "a la MAJ" % BUILD_CAPTURE)
    if old_tr.get("Resilient") != cur_tr.get("Resilient"):
        ko += 1
        print("[2] BLOQUANT : Resilient a change d'ordinal -- la derive de trait serait un "
              "changement d'ENUM, pas de gameconfig")
    gc = G.unit("necroOverlord") or {}
    porteurs = []
    idx = G._index()
    for bucket in ("lineup", "npc", "summons"):
        for uid, u in (idx.get(bucket) or {}).items():
            if "MartialApotheosis" in (u.get("passiveAbilities") or []):
                porteurs.append("%s/%s" % (bucket, uid))
    print("[2] gameconfig VIVANT : necroOverlord.passiveAbilities=%r traits=%r"
          % (gc.get("passiveAbilities"), gc.get("traits")))
    print("[2] gameconfig VIVANT : porteurs de MartialApotheosis = %r (config d'ability encore "
          "presente : %s)" % (porteurs, G.ability("MartialApotheosis") is not None))
    if gc.get("passiveAbilities") != ["MyWillBeDoneOverlord"]:
        ko += 1
        print("[2] BLOQUANT : le kit vivant de necroOverlord a change -- relire avant d'epingler")
    print("[2] verdict : la CAPTURE est en arriere (le gameconfig de %s ne POUVAIT pas attribuer "
          "une ability absente de son propre enum)" % BUILD_CAPTURE)
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
    print("[3] validate_abilities sur la capture BRUTE     : %d confrontees, %d champ(s) divergent"
          " -- abilities=%r" % (nc_raw, len(d_raw), derivees))
    print("[3] validate_abilities sur le seed RECHARGE     : %d confrontees, %d champ(s) divergent"
          % (nc_l, len(d_loaded)))
    vacuite = bool(derivees) and not d_loaded
    print("[3] verdict : l'ancienne assertion `assert not adiffs` sur le seed recharge etait %s"
          % ("VACUEUSE (elle ne pouvait pas rougir)" if vacuite else "non concluante ici"))
    # Le bloc Units, LUI, traverse le chargement intact : c'est l'asymetrie qui rendait l'autre
    # moitie du meme test rouge.
    print("[3] bloc Units : perime avant chargement=%r, apres chargement=%r (NON rattrape)"
          % (sorted(CI.stale_unit_entries(raw)), sorted(CI.stale_unit_entries(loaded))))
    return 0


# --------------------------------------------------------------------------- etape 4

def step_mutations() -> int:
    """Chaque garde du fichier offline doit ROUGIR quand on neutralise une moitie de son objet."""
    import tests.engine.runner.test_catalog_inject_offline as T

    save = {"pin": CI.STALE_UNIT_ENTRIES, "traits": CI._traits,
            "refresh": CI.refresh_ability_configs, "build": T.BUILD_DE_LA_CAPTURE,
            "raw": T._raw_seed}

    def restore():
        CI.STALE_UNIT_ENTRIES = save["pin"]
        CI._traits = save["traits"]
        CI.refresh_ability_configs = save["refresh"]
        T.BUILD_DE_LA_CAPTURE = save["build"]
        T._raw_seed = save["raw"]

    def raw_corrige():
        bc = save["raw"]()
        for u in bc["Units"]:
            if u.get("Id") == "necroOverlord":
                u["PassiveAbilities"] = [1556]
                u["Traits"] = ["Xenos", "Hero", "LivingMetal", "Mechanical", "Resilient"]
        return bc

    vrai_traits = save["traits"]
    fidelite = T.test_la_synthese_reproduit_le_catalogue_capture_hors_derive_epinglee
    epingle = T.test_le_bloc_units_perime_est_exactement_celui_qui_est_epingle
    attribution = T.test_la_derive_du_bloc_units_est_attribuee_a_la_migration_de_build
    asymetrie = T.test_le_chargement_rafraichit_abilities_et_utilities_mais_PAS_units
    abilities = T.test_le_rattrapage_repare_exactement_les_configs_dability_qui_derivent

    def pin_vide():
        CI.STALE_UNIT_ENTRIES = {}

    def pin_orpheline():
        CI.STALE_UNIT_ENTRIES = dict(save["pin"], ultraTitus=("Traits",))

    def synthese_amputee():
        CI._traits = lambda gc: vrai_traits(gc)[:-1]

    def mauvais_build():
        T.BUILD_DE_LA_CAPTURE = symbols_layout.current_build()

    def rattrapage_inerte():
        CI.refresh_ability_configs = lambda bc, skip=(), withhold=(): ([], [])

    def capture_corrigee():
        T._raw_seed = raw_corrige

    cas = [
        ("epingle VIDE            -> fidelite", pin_vide, fidelite),
        ("epingle VIDE            -> epingle", pin_vide, epingle),
        ("epingle VIDE            -> asymetrie", pin_vide, asymetrie),
        ("epingle ORPHELINE       -> epingle", pin_orpheline, epingle),
        ("synthese AMPUTEE        -> fidelite", synthese_amputee, fidelite),
        ("attribution MAUVAIS BUILD -> attribution", mauvais_build, attribution),
        ("rattrapage INERTE       -> abilities", rattrapage_inerte, abilities),
        ("capture CORRIGEE        -> asymetrie", capture_corrigee, asymetrie),
    ]
    ko = 0
    for nom, mutation, test in cas:
        restore()
        mutation()
        try:
            test()
        except AssertionError as e:
            etat, detail = "ROUGE", str(e).splitlines()[0][:80]
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
