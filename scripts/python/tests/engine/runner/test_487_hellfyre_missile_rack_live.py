"""`1088 HellfyreMissileRack` (thousTerminator « Toth ») FACE COMBAT (execute) confrontee LIVE.

`IdunBattleLogic.Entities.Abilities.Active.Loki.HellfyreMissileRackAbility$$ExecuteBehaviour`
(DECOMPILE) :

    atk1/atk2 = DSLBehaviors.AbilityDamage(Caster@+0x48, ActiveTarget@+0x68, MinMaxDamage,
                    Direct(GetDamageProfile) = HeavyRound, Get(GetNumberConstant(0x2f) = nrOfHits),
                    <AbilityOrEffect 1088>, isOutsideAttack = false, selectionType = 2)
    extra     = DSLSelectors.FromTrigger(
                    DSLSelectors.NonSteppableOrObjectUnits(
                        DSLSelectors.Enemies(Caster@+0x48, AllUnits@+0x20, 3), 3),
                    DSLTriggers.HasTakenDamageOfDamageProfileThisTurn(ActiveTarget@+0x68, 0xd), 0)
    AActiveAbility.Execute(entities, this,
        DSLBehaviors.SortedAttackSeries(Caster@+0x48, Target@+0x60, atk1, extra, atk2, ...))

AVANT ce port (#487), 1088 etait absente d'`ABILITY_CLASSES` -> `ported:False` = **0 degat, 0 effet,
aucune erreur** (divergence d'etat SILENCIEUSE). Ce fichier est le GARDE de non-regression de ce trou.

Ce que ces tests PROUVENT (montage `probe_487_hellfyre_missile_rack.run`, cf. sa docstring pour la
geometrie et pourquoi le rejeu offline part d'AVANT l'armement) :
  (1) `ported` VRAI -- le garde du no-op silencieux.
  (2) VOLET 1 : la cible designee encaisse `nrOfHits` coups HeavyRound.
  (3) VOLET 2 : CHAQUE ennemi ayant encaisse du **Psychic** ce tour en encaisse `nrOfHits` de plus --
      **la cible du message COMPRISE** quand elle est dans ce cas (i2 : « which can include the
      initial target again »), ce qui lui fait 2 coups.
  (4) TEMOIN NEGATIF : un ennemi VIVANT, a portee, mais SANS Psychic n'est PAS frappe -> le predicat
      `HasTakenDamageOfDamageProfileThisTurn` mord vraiment (sans lui, un volet 2 degenere en « tous
      les ennemis » passerait (2) et (3)).
  (5) CONTRE-CAS : sans aucun Psychic prealable, le volet 2 est VIDE (il n'est pas un forfait).
  (5bis) DOUBLEMENT CONDITIONNEL : caste sur le TEMOIN (non arme) alors que d'autres LE sont, la
      cible ne prend qu'`nrOfHits` -- le 2e volet vient du PREDICAT, pas d'un forfait « la cible
      compte deux fois ». Ce regime est aussi le seul a exercer un TROISIEME etat du MT (montant
      `5984`, contre `2792` arme et `1463` non arme), donc a prouver que la comparaison per-coup
      n'est pas degeneree.
  (6) FIDELITE DU DEGAT : per-coup offline == per-coup live, coup par coup (meme MT seede) -- ce qui
      valide d'un bloc bornes/profil/percage ET l'ordre (qui fixe la sequence de tirages).

⚠ `--seed` NE FAIT PAS varier le MT du runner (mesure #487 : 777 et 31337 rendent le MEME per-coup).
Rejouer ces tests « sur un autre seed » ne generalise donc RIEN sur la consommation de RNG ; ce sont
les TROIS REGIMES ci-dessus qui le font, en changeant l'etat du MT au moment du cast.

RESIDU CONNU, HORS PORT : `receivedDamageThisTurn` (`ActorStatisticsComponent+0x80`) n'est expose par
AUCUN canal de seed -- c'est pour cela que le montage rejoue l'armement offline plutot que de le
seeder. Consequence generale (deja portee par WeaverOfFate/RealityUnbound, pas neuve ici) : un rejeu
offline partant d'un etat capture EN MILIEU DE TOUR sous-estime le volet 2.

Lit l'etat LIVE, aucune tuile/RVA hardcodee. ASCII only (console Windows cp1252).
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce fichier puisse changer de verdict (#486-r12/#486-r15).
DECLENCHEUR = {
    "chemins": (
        # LARGE, ET C'EST UN RESULTAT (doctrine `declencheur_cliquet.py` : le doute se resout
        # TOUJOURS du cote large). Une premiere version enumerait la chaine attendue -- la
        # confrontation a l'empreinte a rendu **69 chemins lus hors perimetre** : un cast live
        # traverse le moteur ENTIER (`ai/`, `playbook/`, `utilities/`, `streams/`, `board.py`,
        # `catalog_inject.py`, ...), pas seulement `abilities/` + `operations/`. Un declencheur
        # etroit aurait fabrique un FAUX VERT (le fichier non rejoue alors que son gisement se
        # rouvre), exactement ce que ce cliquet combat.
        "scripts/python/**/*.py",
        # Entrees VERSIONNEES du montage : le seed BC et les boards.
        "data/seed-bc.json", "data/boards/**",
    ),
    # Le verdict compare le PORT au JEU : un changement de build (gameconfig 1088, formule de
    # degat native) peut le faire basculer sans qu'un seul fichier du depot bouge.
    "build": True,
    "toujours": False,
    "raison": "Un cast confronte LIVE traverse le moteur Python ENTIER (arbre DSL, operations de "
              "degat qui alimentent `received_damage_this_turn`, chargement d'etat, MT) plus son "
              "montage (`probe_487`, `rl_duel`, `board.py`, `catalog_inject.py`) : le perimetre "
              "MESURE est de 69 chemins au-dela d'une enumeration a la main, d'ou le glob large. "
              "`build: True` parce que les bornes / `nrOfHits` / `damageProfile` viennent du "
              "gameconfig du JEU, hors arbre -- un changement de build peut basculer le verdict "
              "sans qu'un fichier du depot bouge.",
}

import gameconfig as GC                                  # noqa: E402

import probe_487_hellfyre_missile_rack as HFMR           # noqa: E402

ABILITY = 1088


def _nr_of_hits() -> int:
    """`AbilityConfiguration.GetNumberConstant(cfg, 0x2f = nrOfHits)` = gameconfig 1088."""
    return int(((GC.ability("HellfyreMissileRack") or {}).get("constants") or {}).get("nrOfHits") or 0)


def _profile() -> str:
    return str(((GC.ability("HellfyreMissileRack") or {}).get("constants") or {}).get("damageProfile"))


def test_hellfyre_config_is_the_source(live_session):
    """Garde de SOURCE : le port lit `nrOfHits`/`damageProfile` du gameconfig, pas un litteral. Si
    l'une des deux cles disparait, tout le reste du fichier mesurerait du vide sans le dire."""
    assert _nr_of_hits() > 0, "constante nrOfHits absente du gameconfig 1088"
    assert _profile() == "HeavyRound", (
        f"damageProfile 1088 = {_profile()!r} != 'HeavyRound' (le profil INFLIGE ; le profil TESTE "
        "par le trigger est Psychic -- ne pas les confondre)")


def test_hellfyre_armed_live(hellfyre_case):
    """ARME (Doombolt Psychic avant) : nrOfHits sur la cible + nrOfHits sur CHAQUE ennemi qui a pris
    du Psychic ce tour, cible comprise ; temoin hors-Psychic epargne ; per-coup bit-exact."""
    h = _nr_of_hits()
    r = hellfyre_case(arm=True)
    diag = r["diag_hf"]
    assert diag.get("ported"), (
        f"ability {ABILITY} non routee par le wiring ability-exec (no-op SILENCIEUX): {diag}")
    lc, oc = HFMR.counts(r["live_hf"]), HFMR.counts(r["off_hf"])
    armed = set(HFMR.counts(r["live_db"]))
    print(f"\n[HELLFYRE arme] cible=u{r['target']} armes={sorted(armed)} temoins={r['witness']}")
    print(f"[HELLFYRE arme] live={lc} off={oc} ordre={diag.get('order')}")

    # (0) le montage a bien ARME quelqu'un, sinon rien de ce qui suit ne discrimine
    assert armed, f"armement Psychic VIDE -- la mesure ne prouve rien (live_db={r['live_db']})"
    assert r["witness"], "aucun temoin hors-Psychic -- l'etage negatif n'est pas exerce"
    # (0bis) l'armement doit etre d'accord des deux cotes, sinon (2) comparerait deux ensembles
    # differents pour une raison qui n'est PAS Hellfyre.
    assert HFMR.counts(r["off_db"]) == HFMR.counts(r["live_db"]), (
        f"armement Doombolt OFF {HFMR.counts(r['off_db'])} != LIVE {HFMR.counts(r['live_db'])} "
        "-- ecart d'ARMEMENT, pas de Hellfyre : la geometrie du montage doit le rendre deterministe")

    # (1) VOLET 1 + (2) VOLET 2 : la cible prend 2*h (elle est armee), les autres armes h
    assert lc.get(r["target"]) == 2 * h, (
        f"cible u{r['target']} : LIVE {lc.get(r['target'])} coups != 2 x nrOfHits ({2 * h}) "
        "-- l'i2 dit « which can include the initial target again »")
    for uid in armed - {r["target"]}:
        assert lc.get(uid) == h, f"arme u{uid} : LIVE {lc.get(uid)} coups != nrOfHits {h}"
    # (3) TEMOIN NEGATIF : hors-Psychic -> jamais frappe, ni live ni offline
    for uid in r["witness"]:
        assert uid not in lc, f"temoin hors-Psychic u{uid} frappe LIVE : {lc}"
        assert uid not in oc, f"temoin hors-Psychic u{uid} frappe OFFLINE : {oc}"
    # (4) ensemble frappe == {cible} U {armes}, des DEUX cotes
    assert set(lc) == {r["target"]} | armed, f"LIVE frappe {sorted(lc)} != cible+armes"
    assert oc == lc, f"coups OFFLINE {oc} != LIVE {lc}"
    # (5) DEGAT bit-exact, coup par coup (valide bornes/profil/percage ET l'ordre des tirages)
    assert r["off_hf"] == r["live_hf"], (
        f"per-coup OFFLINE != LIVE\noff ={r['off_hf']}\nlive={r['live_hf']}")
    print("[HELLFYRE arme] OK : volet1+volet2+temoin+per-coup bit-exact")


def test_hellfyre_target_not_armed_live(hellfyre_case):
    """CIBLE NON ARMEE alors que d'AUTRES le sont : la cible prend `nrOfHits` (volet 1 SEUL) et
    chaque arme `nrOfHits` (volet 2). C'est le contre-cas exact du doublement : si le port comptait
    la cible deux fois par forfait, elle prendrait `2 x nrOfHits` ici aussi."""
    h = _nr_of_hits()
    r = hellfyre_case(arm=True, target_mode="witness")
    diag = r["diag_hf"]
    assert diag.get("ported"), f"ability {ABILITY} non routee : {diag}"
    lc, oc = HFMR.counts(r["live_hf"]), HFMR.counts(r["off_hf"])
    armed = set(HFMR.counts(r["live_db"]))
    print(f"\n[HELLFYRE cible non armee] cible=u{r['target']} armes={sorted(armed)} live={lc}")
    assert armed, f"armement Psychic VIDE -- la mesure ne prouve rien (live_db={r['live_db']})"
    assert r["target"] not in armed, (
        f"la cible u{r['target']} est ARMEE -- ce regime ne discrimine plus (armes={sorted(armed)})")
    assert lc.get(r["target"]) == h, (
        f"cible NON armee u{r['target']} : LIVE {lc.get(r['target'])} coups != nrOfHits {h} "
        "-- le doublement serait un FORFAIT, pas le predicat")
    for uid in armed:
        assert lc.get(uid) == h, f"arme u{uid} : LIVE {lc.get(uid)} coups != nrOfHits {h}"
    assert set(lc) == {r["target"]} | armed, f"LIVE frappe {sorted(lc)} != cible+armes"
    # ORDRE d'insertion du `SortedAttackSeries` : la cible (selecteur 1) AVANT les armes (selecteur 2)
    assert diag.get("order") and diag["order"][0] == r["target"], (
        f"ordre {diag.get('order')} : la cible du volet 1 doit venir EN TETE")
    assert oc == lc, f"coups OFFLINE {oc} != LIVE {lc}"
    assert r["off_hf"] == r["live_hf"], (
        f"per-coup OFFLINE != LIVE\noff ={r['off_hf']}\nlive={r['live_hf']}")
    print("[HELLFYRE cible non armee] OK : volet1 seul sur la cible + ordre + per-coup bit-exact")


def test_hellfyre_unarmed_live(hellfyre_case):
    """CONTRE-CAS (aucun Psychic ce tour) : le volet 2 est VIDE -> nrOfHits sur la SEULE cible."""
    h = _nr_of_hits()
    r = hellfyre_case(arm=False)
    diag = r["diag_hf"]
    assert diag.get("ported"), f"ability {ABILITY} non routee : {diag}"
    lc, oc = HFMR.counts(r["live_hf"]), HFMR.counts(r["off_hf"])
    print(f"\n[HELLFYRE non arme] cible=u{r['target']} live={lc} off={oc} ordre={diag.get('order')}")
    assert lc == {r["target"]: h}, (
        f"sans Psychic prealable : LIVE {lc} != {{cible: {h}}} -- le volet 2 serait un FORFAIT")
    assert not diag.get("extra"), (
        f"le port a produit un volet 2 sans aucun Psychic ce tour : {diag.get('extra')}")
    assert oc == lc, f"coups OFFLINE {oc} != LIVE {lc}"
    assert r["off_hf"] == r["live_hf"], (
        f"per-coup OFFLINE != LIVE\noff ={r['off_hf']}\nlive={r['live_hf']}")
    print("[HELLFYRE non arme] OK : volet 2 vide + per-coup bit-exact")
