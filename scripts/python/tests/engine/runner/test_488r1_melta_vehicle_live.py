"""#488-r1 -- GARDE du verdict « `1211 OnMeltaDamageAbility` est VIVANTE » et de son port.

CE QUE CE FICHIER EMPECHE, et c'est arrive DEUX FOIS sur cette meme ability :

  (a) qu'un futur build RETIRE le +50 % vs `Vehicle` sans qu'on le voie. Les tests qui ne
      confrontent que « port == port » resteraient verts. Ici l'oracle est le NATIF : si le jeu
      cesse d'appliquer le bonus, l'etage [1] rougit et dit qu'il faut RE-CLASSER, pas patcher.
  (b) qu'on re-conclue DEAD-CODE sur une ABSENCE. `case-72` l'a fait sur `gqfc5mff6c` par deux
      raisonnements faux -- « le symbole n'est pas dans la table » (les tables sont indexees par
      ADRESSE, et IL2CPP DEDUPLIQUE les corps triviaux) et « aucun effet observe » (le canal
      employe, `decisionView.effects`, est une vue PAR UNITE, alors que l'effet est pose sur une
      TUILE). L'etage [0] mesure la seule chose qui tranche : le slot de vtable de l'INSTANCE.

ETAGES :
  [0] VTABLE   -- `OnMeltaDamageAbility` DECLARE-t-elle `CreateTrigger` ? (profondeur 0). Avec son
                  CONTRE-CAS : `GetTargetTiles`, que seul `OnFireDamageAbility` declare, doit
                  rendre « absente » pour les deux autres -- sans quoi l'etage ne discrimine rien
                  et son « profondeur 0 » ne vaudrait rien.
  [1] NATIF    -- le +50 % EXISTE-t-il dans le jeu ? Bande contre un `Vehicle` vs DEUX temoins
                  non-`Vehicle`, armure EGALISEE et geometrie IDENTIQUE. Deux temoins et pas un :
                  un seul ne distinguerait pas « le gate Vehicle mord » d'une particularite de
                  cette cible-la.
  [2] PORT     -- le port ACCORDE-t-il avec le natif sur les trois ?
  [3] MORSURE  -- CONTRE-EPREUVE : sans `MATCH_WIDE_EFFECTS`, le port doit DIVERGER sur le
                  `Vehicle` SEUL et rester INCHANGE sur les temoins. Sans ce bras, l'accord de [2]
                  ne prouverait pas que le correctif y est pour quelque chose.
  [4] GATE     -- les conjoints du gate, un par un (profil, trait de cible, cles absentes).

Le montage et toutes les lectures vivent dans `probe_488r1_onmelta_vivant.py` : le probe MESURE,
ce fichier GARDE -- une seule implementation, aucune divergence possible.

Lit l'etat LIVE, aucune RVA ni tuile codee en dur hors du montage, ASCII only.
"""
from __future__ import annotations

import pytest

import probe_488r1_onmelta_vivant as P

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    # PERIMETRE LARGE, et c'est une MESURE : ce fichier importe le PROBE, dont la fermeture
    # d'import atteint la quasi-totalite de `scripts/python` (il monte une `Scene` de prediction).
    # ⚠ Les DEUX formes sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py`
    # ne voit PAS `scripts/python/board.py`.
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py",
                "scripts/python/tests/conftest.py", "scripts/python/tests/engine/conftest.py",
                "data/seed-bc.json", "data/boards/**", "data/symbols/**"),
    # Le NATIF est l'oracle des etages [0] a [3] : un changement de build peut les faire changer
    # d'avis sans qu'une ligne du port bouge -- c'est PRECISEMENT le gisement de cette tranche.
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE port-vs-natif du +50 % `Melta` vs `Vehicle` (effet 1297, pose par "
              "l'ability GLOBALE 1211 au `MatchInit`). Le verdict depend du code du port (le mirror "
              "`MeltaExtraDmgEffect`, son inscription dans `MATCH_WIDE_EFFECTS`, la boucle PARTAGEE "
              "`_attacker_effect_bonuses` -- donc TOUT le pipeline de degat, prediction ET combat --, "
              "le threading d'`att_ctx['damage_profile']` par les deux faces, et la `Scene` de "
              "prediction), du MONTAGE (le probe, qui porte le drive des positions, l'egalisation "
              "d'armure et TOUTES les lectures), des entrees versionnees du runner, et du BUILD "
              "charge -- l'oracle des etages [0] a [3] et [5] etant le jeu lui-meme. Ce dernier point "
              "n'est pas theorique : ce meme verdict a DEJA change entre deux builds (`gqfc5mff6c` "
              "n'avait pas le `CreateTrigger` de 1211, `rnca9r7q6c` l'a).",
}

TOLERANCE = 2          # arrondis Fix64 sur le rapport 3/2 (mesure : 9014 pour 6008x1,5 = 9012)


# --------------------------------------------------------------------------- montage
@pytest.fixture(scope="module")
def montage(rpc, build_runner):
    """Un runner PAR cible (le `Vehicle` et les deux temoins), meme geometrie, meme seed.

    Trois runners et non un seul avec trois cibles : `--armor-target` force l'armure de TOUT le
    camp adverse, et surtout la DISTANCE doit etre la meme pour les trois -- deux cibles sur le
    meme plateau ne peuvent pas occuper la meme tuile."""
    out = {}
    for cible in (P.CIBLE_VEHICLE,) + P.CIBLES_TEMOIN:
        rid = build_runner("777", board=P.BOARD, extra=P.build_extra(cible))["rid"]
        dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 200) or {}
        by_vis = {u.get("visualId"): u for u in (dec.get("units") or [])}
        assert P.CASTER in by_vis and cible in by_vis, (
            "montage KO pour %s : unites presentes = %r" % (cible, sorted(by_vis)))
        out[cible] = (rid, int(by_vis[P.CASTER]["id"]), int(by_vis[cible]["id"]))
    return out


def _bandes(rpc, rid, aid, tid):
    return P.bandes(lambda m, b=None, t=120: rpc(m, b, t), rid, aid, tid)


# --------------------------------------------------------------------------- [0] vtable
def test_etage0_la_classe_declare_bien_son_create_trigger(rpc):
    """[0] `OnMeltaDamageAbility` DECLARE `CreateTrigger` -- profondeur 0 du 1er corps.

    C'est la SEULE mesure qui tranche : le corps `On(MatchInit, true)` est DEDUPLIQUE (son adresse
    porte 8 xrefs DATA contre 2 chez les jumeaux), donc ni la presence ni l'absence du symbole dans
    `ghidra/functions.tsv` ne prouvent quoi que ce soit sur la classe."""
    cibles = [{"ns": P.NS_DMG, "cls": c, "method": m} for c in P.FAMILLE for m in P.METHODES]
    res = rpc("resolveMethodPtr", {"targets": cibles, "maxDepth": 6}, 90)
    assert res and res.get("ok"), "RPC resolveMethodPtr KO : %r" % (res,)
    prof = {}
    for t in res["targets"]:
        d = None
        if t.get("ok"):
            for niveau in t["levels"]:
                if niveau["methods"]:
                    d = niveau["depth"]
                    break
        prof[(t["cls"], t["method"])] = d

    assert prof[("OnMeltaDamageAbility", "CreateTrigger")] == 0, (
        "OnMeltaDamageAbility ne DECLARE PAS CreateTrigger (profondeur %r) -- le verdict DEAD-CODE "
        "de `case-72` redeviendrait vrai. NE PAS patcher le port : RE-CLASSER l'ability et "
        "re-mesurer les etages [1]-[3]." % (prof[("OnMeltaDamageAbility", "CreateTrigger")],))

    # CONTRE-CAS : sans lui, un etage qui rendrait « profondeur 0 » pour tout passerait pour vert.
    assert prof[("OnMeltaDamageAbility", "GetTargetTiles")] is None, (
        "l'etage NE DISCRIMINE PLUS : `GetTargetTiles` n'est declaree que par OnFireDamageAbility, "
        "elle doit etre ABSENTE de la chaine d'OnMelta (obtenu : %r)"
        % (prof[("OnMeltaDamageAbility", "GetTargetTiles")],))
    assert prof[("OnFireDamageAbility", "GetTargetTiles")] == 0, (
        "temoin de morsure INOPERANT : OnFireDamageAbility doit DECLARER GetTargetTiles")


# --------------------------------------------------------------------------- [1] le natif
def test_etage1_le_natif_applique_bien_50pct_contre_vehicle(rpc, montage):
    """[1] LE VERDICT LUI-MEME, pris sur le jeu. Mesure de reference (`MC1_67`/777, armure 2000) :
    `admecDestroyer` (Vehicle) [9014-13520] contre [6008-9014] pour les DEUX temoins -- rapport
    1,50033 / 1,49989.

    ⚠ Si CE test rougit, le port n'est pas en cause : c'est le JEU qui a change d'avis."""
    veh = _bandes(rpc, *montage[P.CIBLE_VEHICLE])[1]
    assert veh[0] > 0 and veh[1] > veh[0], (
        "bande degeneree cote Vehicle (%r) : le montage ne mesure rien" % (veh,))
    for temoin in P.CIBLES_TEMOIN:
        ref = _bandes(rpc, *montage[temoin])[1]
        assert ref[0] > 0, "bande degeneree pour le temoin %s (%r)" % (temoin, ref)
        for i, borne in enumerate(("min", "max")):
            attendu = ref[i] * 3 // 2
            assert abs(veh[i] - attendu) <= TOLERANCE, (
                "le +50 %% vs Vehicle N'EST PLUS applique par le NATIF : borne %s = %d contre %d "
                "attendu (1,5 x %d, temoin %s). RE-CLASSER l'ability avant de toucher au port."
                % (borne, veh[i], attendu, ref[i], temoin))


def test_etage1b_les_deux_temoins_non_vehicle_coincident(rpc, montage):
    """[1b] NON-DEGENERESCENCE du temoin : les deux cibles non-`Vehicle` doivent rendre la MEME
    bande. Sinon l'ecart mesure en [1] pourrait tenir a la cible plutot qu'a son trait."""
    a, b = (_bandes(rpc, *montage[t])[1] for t in P.CIBLES_TEMOIN)
    assert a == b, ("les deux temoins non-Vehicle divergent (%r vs %r) : le montage ne neutralise "
                    "pas tout sauf le trait, l'etage [1] n'est donc pas attribuable" % (a, b))


# --------------------------------------------------------------------------- [2] le port
@pytest.mark.parametrize("cible", (P.CIBLE_VEHICLE,) + P.CIBLES_TEMOIN)
def test_etage2_le_port_accorde_avec_le_natif(rpc, montage, cible):
    """[2] ACCORD port/natif sur les TROIS cibles -- bornes comprises."""
    port, natif = _bandes(rpc, *montage[cible])
    assert port is not None, "le port ne rend AUCUNE prediction pour %s" % cible
    assert port == natif, ("le port DIVERGE du natif sur %s : port=%r natif=%r (ecart %r)"
                           % (cible, port, natif, (port[0] - natif[0], port[1] - natif[1])))


# --------------------------------------------------------------------------- [3] la morsure
def test_etage3_sans_le_correctif_le_port_diverge_sur_le_vehicle_seul(rpc, montage, monkeypatch):
    """[3] CONTRE-EPREUVE. On VIDE `MATCH_WIDE_EFFECTS` -- le port perd le +50 % Melta, et RIEN
    d'autre. Il doit alors DIVERGER sur le `Vehicle` et rester INCHANGE sur les deux temoins.

    Mesure de reference : ecart `(-3006, -4506)` sur `admecDestroyer`, `(0, 0)` sur les temoins.

    Sans ce bras, l'accord de [2] pourrait venir d'ailleurs (« verifier que la MUTATION a mordu »).
    Le patch vise l'ATTRIBUT DE MODULE `_MATCH_WIDE_EFFECTS`, que `match_wide_effects()` relit a
    chaque appel -- forme B, la seule qui morde."""
    from engine.entities import effects as EF
    monkeypatch.setattr(EF, "_MATCH_WIDE_EFFECTS", [])

    port_v, natif_v = _bandes(rpc, *montage[P.CIBLE_VEHICLE])
    assert port_v != natif_v, (
        "CONTRE-EPREUVE INOPERANTE : le port accorde encore (%r) alors que `MATCH_WIDE_EFFECTS` est "
        "vide -- le +50 %% vient donc d'AILLEURS que du correctif de #488-r1, et ce fichier ne "
        "garde pas ce qu'il pretend garder" % (port_v,))
    assert port_v[0] < natif_v[0] and port_v[1] < natif_v[1], (
        "sens de l'ecart INATTENDU : sans le bonus le port doit SOUS-estimer (%r vs %r)"
        % (port_v, natif_v))

    for temoin in P.CIBLES_TEMOIN:
        port_t, natif_t = _bandes(rpc, *montage[temoin])
        assert port_t == natif_t, (
            "le correctif MORD HORS de son regime : sans lui, %s (non-Vehicle) devrait etre "
            "INCHANGE, or port=%r natif=%r. Le rayon de souffle deborde." % (temoin, port_t, natif_t))


# --------------------------------------------------------------------------- [5] l'axe ABILITY
@pytest.fixture(scope="module")
def montage_ability(rpc, build_runner):
    """`bloodDante` (lineup) castant `LightOfSanguinius`, dont le `damageProfile` est `Melta`."""
    rid = build_runner("777", board=P.BOARD,
                       extra=P.build_extra_ability(P.CIBLE_VEHICLE))["rid"]
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 200) or {}
    by_vis = {u.get("visualId"): u for u in (dec.get("units") or [])}
    assert P.CASTER_ABILITY in by_vis and P.CIBLE_VEHICLE in by_vis, (
        "montage ABILITY KO : %r" % sorted(by_vis))
    return rid, int(by_vis[P.CASTER_ABILITY]["id"]), int(by_vis[P.CIBLE_VEHICLE]["id"])


def test_etage5_le_bonus_vaut_aussi_pour_une_ABILITY_a_profil_melta(rpc, montage_ability,
                                                                    monkeypatch):
    """[5] GENERALISATION -- autre PORTEUR, autre VECTEUR, autre ORACLE.

    Le gate natif porte sur le PROFIL DU COUP, jamais sur le vecteur : sur ce build, `Melta` est
    porte par 2 armes de lineup ET par 6 abilities. Ne confronter que l'arme laisserait la moitie du
    rayon non mesuree. Ici : `bloodDante` (et non `tauShadowsun`) caste `LightOfSanguinius` (voie
    ACTIVE, et non l'attaque normale), confronte a `aiPlaybookPredict` (et non `aiPredict`).

    Mesure de reference : natif `(8840, 13270)` == port ; sans le correctif, port `(5890, 8845)`
    -- rapport 1,5008 / 1,5003."""
    rid, aid, tid = montage_ability
    port, natif = P.bandes_ability(lambda m, b=None, t=120: rpc(m, b, t), rid, aid, tid)
    assert natif, "l'oracle natif n'a rendu aucun event pour la cible"
    assert port == natif, ("axe ABILITY : le port DIVERGE du natif -- port=%r natif=%r"
                           % (port, natif))

    # CONTRE-EPREUVE : le meme bras sans le correctif doit SOUS-estimer d'un facteur ~1,5.
    from engine.entities import effects as EF
    monkeypatch.setattr(EF, "_MATCH_WIDE_EFFECTS", [])
    sans, _ = P.bandes_ability(lambda m, b=None, t=120: rpc(m, b, t), rid, aid, tid)
    assert sans != port, (
        "CONTRE-EPREUVE INOPERANTE sur l'axe ABILITY : le port rend %r avec ET sans "
        "`MATCH_WIDE_EFFECTS` -- le +50 %% viendrait donc d'ailleurs" % (sans,))
    assert sans and sans[0][1] < port[0][1], (
        "sens de l'ecart INATTENDU : sans le bonus le port doit SOUS-estimer (%r vs %r)"
        % (sans, port))


# --------------------------------------------------------------------------- [4] le gate
def test_etage4_les_deux_conjoints_du_gate_mordent_un_par_un():
    """[4] OFFLINE -- `ForPercentIncrease(DamageProfileHasTrait(OnMelta) & HasTrait(target,
    Vehicle), 50)`, conjoint par conjoint, plus les deux cles ABSENTES.

    Une cle absente doit FERMER le gate (degradation RESTRICTIVE) : un `att_ctx` sans profil ne
    veut pas dire « profil quelconque »."""
    from engine.entities.effects import match_wide_effects
    from engine.entities.traits.unit_trait import UnitTrait

    mw = match_wide_effects()
    assert [type(e).__name__ for e in mw] == ["MeltaExtraDmgEffect"], (
        "MATCH_WIDE_EFFECTS a change de composition : %r" % ([type(e).__name__ for e in mw],))
    eff = mw[0]
    veh = frozenset({UnitTrait.Vehicle.name})

    def bonus(profil, traits):
        return eff.create_effect_damage_bonus_for_attack(
            target_traits=traits, att_ctx=({} if profil is None else {"damage_profile": profil}))

    ok = bonus("Melta", veh)
    assert ok is not None and int(ok.value) == 50 and ok.kind == "PercentIncrease", (
        "le regime NOMINAL ne rend pas +50 %% : %r" % (ok,))
    assert bonus("Melta", frozenset({"BigTarget"})) is None, "gate `HasTrait(target, Vehicle)` MUET"
    assert bonus("Physical", veh) is None, "gate `DamageProfileHasTrait(OnMelta)` MUET"
    assert bonus(None, veh) is None, "profil ABSENT : le gate doit se FERMER, pas s'ouvrir"
    assert bonus("Melta", None) is None, "traits de cible ABSENTS : le gate doit se FERMER"
