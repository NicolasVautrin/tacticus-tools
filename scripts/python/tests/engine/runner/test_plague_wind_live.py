"""PlagueWind (actif 1035, deathTyphus « Typhus », Death Guard) PORT -> arbre DSL, confronte au LIVE.

`IdunBattleLogic.Entities.Abilities.Active.Loki.PlagueWindAbility$$ExecuteBehaviour` (DECOMPILE,
mirror 1:1, cf. `engine/runner/abilities/deathguard.py`) = AoE CONCENTRIQUE a TROIS bandes :

    t1 = Cache(target@0x178)                                            -> MinMaxDamage  (minDmg  /maxDmg  )
    t2 = Cache(Enemies(caster, AdjacentUnits(t1)))                      -> MinMaxDamage2 (minDmg_2/maxDmg_2)
    t3 = Cache(Unique(Enemies(AdjacentUnits(t2))) - t1 - t2)            -> MinMaxDamage3 (minDmg_3/maxDmg_3)
    ExecuteAtomic( Group(a1,0x4b) & Group(a2,0x4c) & Group(a3,0x4d) )

nrOfHits = `GetNumberConstant(0x2f)` = 1, LA MEME pour les trois bandes ; profil `Psychic`
(PiercingRatio 100, `NoBlocking`) ; famille ABILITY (`IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` -> 1 tirage
par coup, aucun crit).

CE QUE CE TEST VALIDE (deux cas DISCRIMINANTS ; montage = la fixture NOMMEE `psychic_aoe_case`,
`tests/engine/runner/conftest.py`, qui delegue au probe `scripts/python/probe_psychic_aoe.py`) :
  (A) `pw-solo`  — cible ISOLEE : SEULE la bande 1 tire (secondary/tertiary VIDES) et son degat est
      BIT-EXACT vs le live.
  (B) `pw-chain` — cible + 1 ennemi ADJACENT a la cible + 1 ennemi adjacent a CE secondaire mais a
      distance 2 de la cible : les TROIS bandes tirent, chacune sur SA cible, et les trois degats
      sont BIT-EXACTS vs le live.
  (C) DISCRIMINANCE : un port DELIBEREMENT FAUX (les trois bandes partageant `minDmg`/`maxDmg`, au
      lieu des plages _2/_3) DIVERGE du live sur le meme etat et le meme `state.rng` -> le cas
      SEPARE bien les hypotheses (mesure : live 3706/3306/3476 vs faux-port 3706/4464/6285).

Lit l'etat LIVE (aucune tuile/valeur hardcodee), state-file UNIQUE, dispose au teardown (le probe
s'en charge). ASCII only.
"""
from __future__ import annotations


def test_plague_wind_single_band_live(psychic_aoe_case):
    """(A) Cible ISOLEE -> UNE seule bande. Le port ne doit inventer ni secondaire ni tertiaire, et
    le degat de la bande 1 est bit-exact vs le live."""
    r = psychic_aoe_case("pw-solo")
    diag = r["diag"]
    assert len(diag["main"]) == 1, f"bande 1 attendue sur la seule cible : {diag['main']}"
    assert diag["secondary"] == [] and diag["tertiary"] == [], (
        f"cible isolee -> bandes 2/3 VIDES, obtenu secondary={diag['secondary']} "
        f"tertiary={diag['tertiary']}")
    assert r["exact"], f"degat non bit-exact : live={r['live']} off={r['off']}"
    assert len(r["live"].get(r["target"], [])) == 1, (
        f"nrOfHits=1 attendu sur la cible, live={r['live']}")


def test_plague_wind_three_bands_live(psychic_aoe_case):
    """(B)+(C) Chaine cible -> adjacent -> adjacent-du-secondaire : les TROIS bandes tirent, chacune
    avec SA plage (`minDmg`/`minDmg_2`/`minDmg_3`), bit-exact vs le live ; et la contre-epreuve
    « une seule plage pour tout l'AoE » DIVERGE (le cas est bien discriminant)."""
    r = psychic_aoe_case("pw-chain")
    diag = r["diag"]
    assert len(diag["main"]) == 1, f"bande 1 (cible) attendue : {diag['main']}"
    assert len(diag["secondary"]) == 1, f"bande 2 (adjacent-cible) attendue : {diag['secondary']}"
    assert len(diag["tertiary"]) == 1, f"bande 3 (adjacent-secondaire) attendue : {diag['tertiary']}"
    # les 3 bandes frappent 3 unites DISTINCTES (aucun double-comptage entre bandes)
    hit = [diag["main"][0]["target"], diag["secondary"][0]["target"], diag["tertiary"][0]["target"]]
    assert len(set(hit)) == 3, f"bandes non disjointes : {hit}"
    assert r["exact"], f"degat non bit-exact : live={r['live']} off={r['off']}"
    # un coup par cible (nrOfHits = 1, la MEME constante pour les trois bandes)
    for t in hit:
        assert len(r["live"].get(t, [])) == 1, f"u{t} : 1 coup attendu, live={r['live'].get(t)}"
    assert r["discriminant"], (
        "cas NON discriminant : le port-FAUX (une seule plage pour les 3 bandes) rend le MEME "
        f"resultat que le live -> ce test ne prouverait rien. control={r['control']} "
        f"live={r['live']}")
