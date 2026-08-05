"""#477-r16-r1-r1 -- GARDE offline de la branche de DEDUPLICATION d'`IncludeEnvironmentAbility`.

Le probe `probe_477r16_allocation_entites_ecs.py --contre-dedup` MESURE en live (il monte un
runner par montage, lit le flux, compte les entites allouees avant les tuiles). Ce fichier
GARDE : il fige ce que la mesure a etabli, et surtout il verifie que le modele DISCRIMINE.

POURQUOI LA MOITIE DU TEST EST LA REFUTATION DES CONCURRENTS. Sur le seed courant,
`BC.EnvironmentAbilities` est VIDE : les trois termes qui passent par
`IdunBattle.Operations.SetupGameOperation$$IncludeEnvironmentAbility` valent invariablement
1/1/0, et TROIS modeles differents de `E` rendent alors la MEME valeur (6). Un test qui se
contenterait de « le modele lu reproduit les mesures » passerait donc au vert avec un modele
FAUX. Chaque montage ci-dessous est choisi pour separer au moins deux des trois modeles, et le
test exige que les concurrents soient effectivement REFUTES par les chiffres mesures.

CE QUI EST FIGE ICI vient d'une mesure live NOMMEE (session Frida 8, board `C1_02`, seed 777,
build `rnca9r7q6c`, 2026-08-05), predictions imprimees AVANT la mesure. `E` = le nombre
d'entites allouees entre le dernier joueur et la premiere tuile -- le bloc des environment
abilities, que `IdunBattle.Operations.AddEnvironmentAbilityOperation$$Execute` alloue sans
emettre la moindre action dans le flux.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve()
PY = next(p for p in HERE.parents if p.name == "python")
if str(PY) not in sys.path:
    sys.path.insert(0, str(PY))

import probe_477r16_allocation_entites_ecs as P  # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType as TAT  # noqa: E402


# `E` MESURE en live, par montage. La cle est celle de `P.variantes_dedup()` ; `None` designe le
# seed versionne intact (le temoin).
E_MESURE = {
    None: 6,
    "temoin-positif": 7,
    "dedup-fire": 6,
    "addrange-double": 7,
    "dedup-les-deux": 6,
    "derived-doublon": 8,
}


@pytest.fixture(scope="module")
def regles():
    """{cle de montage: regle derivee}. Aucun runner -- tout est offline."""
    out = {None: P.deriver_regle()}
    for v in P.variantes_dedup():
        if v["path"] is None:
            pytest.skip("montage %s non construisible : %s" % (v["cle"], v["empeche"]))
        out[v["cle"]] = P.deriver_regle(v["path"])
    return out


def test_le_modele_lu_reproduit_les_mesures(regles):
    """Le modele DEDUP rend exactement le `E` mesure, sur les six montages."""
    ecarts = {k: (regles[k]["E_lu"], e) for k, e in E_MESURE.items()
              if regles[k]["E_lu"] != e}
    assert not ecarts, "modele lu != mesure live (cle: (prevu, mesure)) -> %s" % ecarts


def test_les_deux_modeles_concurrents_sont_refutes(regles):
    """SOMME NAIVE et TOUT-DEDUPLIQUE doivent etre FAUX sur au moins un montage chacun.

    Sans cette assertion, `test_le_modele_lu_reproduit_les_mesures` serait satisfait par
    n'importe lequel des trois modeles sur le seul seed intact : c'est exactement le regime
    degenere que cette tranche existe pour quitter.
    """
    for nom, f in (("SOMME NAIVE", P.e_modele_naif),
                   ("TOUT-DEDUPLIQUE", P.e_modele_tout_dedup)):
        faux = [k for k, e in E_MESURE.items() if f(regles[k]) != e]
        assert faux, ("le modele %s reproduit TOUTES les mesures -- aucun montage ne le "
                      "separe du modele lu, le regime est DEGENERE" % nom)


def test_chaque_montage_separe_bien_ce_qu_il_pretend_separer(regles):
    """Un montage qui ne discrimine plus est un montage MORT -- on veut le savoir."""
    attendu = {
        # cle              : les modeles dont la prediction DOIT differer de celle du modele lu
        "dedup-fire": {"naif"},
        "addrange-double": {"naif", "tout_dedup"},
        "dedup-les-deux": {"naif"},
        "derived-doublon": {"tout_dedup"},
    }
    for cle, doivent_differer in attendu.items():
        r = regles[cle]
        prevu = {"dedup": r["E_lu"], "naif": P.e_modele_naif(r),
                 "tout_dedup": P.e_modele_tout_dedup(r)}
        differents = {m for m in ("naif", "tout_dedup") if prevu[m] != prevu["dedup"]}
        assert doivent_differer <= differents, (
            "le montage %s ne separe plus %s (predictions %s)"
            % (cle, sorted(doivent_differer - differents), prevu))


def test_la_forme_serialisee_lue_est_celle_du_converter_natif():
    """`ConfigId` est une CHAINE, et l'extracteur mirror `CreateFromString`.

    `IdunShared.TriggeredAbilityConfigId` porte
    `TriggeredAbilityConfigIdJsonConverter : Idun.Shared.Serialization.StringJsonConverter<T>` :
    un objet JSON n'est PAS une forme valide. Le champ s'appelle `ConfigId` (mesure live,
    RPC `classFields`), pas `Id`.
    """
    assert P.config_id_depuis_json("EnvFireTileDamage") == (int(TAT.EnvFireTileDamage), None)
    # `ToConfigId` ecrit `<nom><separateur><VariantId>` -- seule la partie avant le separateur
    # entre dans `Enum.TryParse`.
    assert P.config_id_depuis_json("EnvFireTileDamage:variante") == (
        int(TAT.EnvFireTileDamage), None)
    # chaine vide / absente -> `{0, null}` (CollectionExtensions.IsNullOrEmpty)
    assert P.config_id_depuis_json("") == (0, None)
    assert P.config_id_depuis_json(None) == (0, None)
    # `Enum.TryParse` en echec : le natif rend 0 et alloue QUAND MEME une entite -- on compte
    # comme lui, mais on NOMME le coupable au lieu de le taire.
    assert P.config_id_depuis_json("PasUneAbility") == (0, "PasUneAbility")


def test_une_forme_hors_converter_est_REMONTEE_jamais_comptee_en_silence():
    """Une forme que le converter natif ne lit pas doit sortir en OPAQUE, pas en zero."""
    bc = {"EnvironmentAbilities": {
        "EnvironmentAbilities": [
            {"ConfigId": "EnvFireTileDamage", "Level": 1, "PlayerId": None},   # lisible
            {"ConfigId": {"AbilityType": "EnvFireTileDamage"}},                # objet -> opaque
            {"Id": "EnvFireTileDamage"},                                       # champ d'avant
        ],
        "EnhancementsEnvironmentAbilities": []}}
    lus, opaques, inconnus = P.ids_env_abilities_du_bc(bc)
    assert lus == [int(TAT.EnvFireTileDamage)]
    assert len(opaques) == 2 and not inconnus


def test_deriver_regle_REFUSE_de_conclure_sur_une_forme_opaque(tmp_path):
    """Un element illisible rend la deduplication INDECIDABLE : on leve, on ne devine pas."""
    src = P.DATA / "seed-bc.json"
    if not src.is_file():
        pytest.skip("seed BC absent : %s (python dump_boards.py)" % src)
    import json
    bc = json.loads(src.read_text(encoding="utf-8"))
    bc.setdefault("EnvironmentAbilities", {})["EnvironmentAbilities"] = [
        {"ConfigId": {"AbilityType": "EnvFireTileDamage"}}]      # forme hors converter
    p = tmp_path / "seed-bc-opaque.json"
    p.write_text(json.dumps(bc), encoding="utf-8")
    with pytest.raises(P.MesureImpossible) as e:
        P.deriver_regle(p)
    assert "illisible" in str(e.value)


def test_l_ordre_derived_vers_include_reste_INOBSERVABLE():
    """Les valeurs de la table `+0x38` et les 3 ids dedupliques sont DISJOINTS sur ce build.

    Tant que l'intersection est vide, l'ordre `boucle derived` -> `IncludeEnvironmentAbility`
    n'a aucun effet observable : aucun id ne peut venir des deux cotes. Si un build la rend non
    vide, ce test ROUGIT -- et c'est le signal qu'un montage doit etre ecrit pour confronter
    l'ordre, plus seulement le lire.
    """
    o = P.ordre_derived_avant_include()
    assert not o["observable"], (
        "l'ordre derived -> Include est devenu OBSERVABLE (intersection %s) : la lecture ne "
        "suffit plus, il faut un montage" % o["intersection"])


def test_chaque_cran_de_verdict_est_capable_de_rougir():
    """Un garde-fou jamais vu rouge n'en est pas un (#430) -- on le verifie a chaque passe."""
    ok, rapport = P.auto_test_gardes()
    assert ok, "au moins un cran est INERTE :\n%s" % "\n".join(rapport)
