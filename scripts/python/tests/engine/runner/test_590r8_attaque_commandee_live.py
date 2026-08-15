"""#590-r8 -- l'attaque commandee de `1101 AttemptedPossession` DOIT aboutir dans le flux du cast.

CE QUE CE FICHIER GARDE, ET POURQUOI IL N'EXISTAIT PAS. Le port posait le bond, le swap d'owner,
l'override et la contrainte de cible correctement, et ne frappait PAS -- sans erreur, sans trace.
Aucun test ne voyait ce no-op : les gardes offline de #590 valident la STRUCTURE de l'arbre (les
cinq feuilles, leur ordre, les selecteurs), et la formule de degat y etait evaluee sous un
contexte PORTANT un `config` factice, alors que `entities_from_state` n'en branche AUCUN. Les deux
etaient verts pendant que l'ability ne faisait rien.

LA CAUSE, MESUREE ETAGE PAR ETAGE (`probe_590r8_flux_du_cast.py`) : le noeud de montant de
l'`AddStatOverrideEffect` lisait ses deux variables par `ConfigVar`, qui lit `ctx.config` -- non
branche. L'override posait donc **ATTACK = 0** sur chaque possede ; le moteur d'utilite ne trouvait
plus aucune action rentable et `perform_ai_ability_unit_behaviour` rendait `None`. Le residu
accusait CE corps (<< foyer PARTAGE par huit call-sites >>) : il etait innocent.

LES QUATRE CRANS, du plus proche de la cause au plus observable :
  1. l'ATTACK de la possedee A L'ENTREE du corps est NON NULLE (le cran exact du bug) ;
  2. le cast PORTE frappe, et frappe la PROIE (camp de la CIBLE) -- l'owner-swap par son
     observable, pas par une lecture de `team` qui vaut la meme chose avant et apres ;
  3. le NATIF frappe la meme unite -- sinon le cran 2 garderait un accord avec rien ;
  4. le montant natif est dans l'ENVELOPPE DE TIRAGE du port. C'est le seul enonce honnete sur le
     MONTANT : un tirage unique de part et d'autre ne peut pas etablir une egalite de formule, et
     exiger l'egalite ferait rougir un port juste.

Montage : celui de `probe_590_attempted_possession.py`, reutilise via `probe_590r8_flux_du_cast.
mesurer` -- une seule implementation du montage, donc aucune divergence possible entre ce qui est
MESURE la-bas et ce qui est GARDE ici.

Montage KO -> `pytest.fail`, JAMAIS un skip (un skip serait un vert qui ment).
ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_RACINE = Path(__file__).resolve().parents[3]
if str(_RACINE) not in sys.path:
    sys.path.insert(0, str(_RACINE))

DECLENCHEUR = {
    # PERIMETRE LARGE et MESURE : ce fichier monte un runner live et rejoue TOUT le port de 1101
    # (arbre + effets + PerformAIAbility + le corps partage + le moteur d'utilite offline). Sa
    # fermeture d'import couvre l'essentiel de `scripts/python`. Declarer etroit = FAUX VERT.
    # Les DEUX formes sont necessaires : `**/` exige un SEGMENT.
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py",
                "data/seed-bc.json", "data/boards/**", "data/symbols/**"),
    "build": True,
    "toujours": False,
    "raison": "Il confronte au NATIF, sur un runner live, le fait que l'attaque commandee de 1101 "
              "aboutit -- donc il depend du port entier de l'ability ET du build charge.",
}


@pytest.fixture(scope="module")
def mesure():
    import probe_590r8_flux_du_cast as P
    try:
        m = P.mesurer("test_590r8_attaque_commandee")
    except SystemExit as exc:
        pytest.fail("montage KO (jamais un skip) : %s" % (exc,))
    except Exception as exc:                     # noqa: BLE001 -- on veut la CAUSE au rapport
        pytest.fail("montage KO (jamais un skip) : %s: %s" % (type(exc).__name__, exc))
    try:
        yield m
    finally:
        m["dispose"]()                            # MES runners, jamais ceux des autres


def _acted(m) -> dict:
    """Le journal `PerformAIAbility` du cast PORTE, pour l'unique acteur possede."""
    ai = ((m["cast"] or {}).get("diag") or {}).get("ai") or []
    assert ai, "le cast n'a emis AUCUN `PerformAIAbility` -- l'arbre n'a pas ete joue"
    acted = (ai[0].get("acted") or [])
    assert acted, "le `PerformAIAbility` n'a agi sur AUCUN acteur"
    return acted[0]


def test_cran1_l_attack_de_la_possedee_est_non_nulle_a_l_entree_du_corps(mesure):
    """LE CRAN EXACT DU BUG. L'override de degat pose `min(maxDmg, dmgPct% x ATTACK_INITIAL)` ;
    quand ses deux variables ne se resolvent pas, il pose **0** -- et tout le reste en decoule."""
    photo = mesure["photo_cast"] or {}
    cible = photo.get("cible")
    assert cible is not None, "la photo d'etat n'a pas ete prise : le corps n'a jamais ete atteint"
    assert cible["atk"], (
        "ATTACK = %r a l'entree du corps : l'override de degat a pose une valeur NULLE (c'est "
        "#590-r8). Verifier que les deux variables du noeud de montant sont RESOLUES par "
        "l'appelant -- `ConfigVar` lit `ctx.config`, que `entities_from_state` ne branche pas."
        % (cible["atk"],))
    # L'effet 1210 EST pose : sans lui, un ATTACK non nul ne prouverait rien (ce serait la valeur
    # naturelle de l'unite, override absent).
    assert 1210 in (cible["effets"] or []), (
        "l'effet 1210 AttemptedPossession_DmgOverride n'est PAS pose a l'entree du corps -- le "
        "cran ci-dessus mesurerait alors l'ATTACK naturelle, pas l'override")


def test_cran2_le_cast_porte_FRAPPE_et_frappe_la_proie(mesure):
    """L'observable de l'owner-swap : la possedee frappe une unite de SON camp d'origine."""
    acted = _acted(mesure)
    res = acted.get("result")
    assert res is not None, (
        "l'attaque commandee n'a pas abouti (`result: null`) -- c'est exactement #590-r8. "
        "acted = %r" % (acted,))
    assert int(res.get("target")) == int(mesure["ids"]["proie"]), (
        "la possedee a frappe %r au lieu de la proie %r (camp de la CIBLE)"
        % (res.get("target"), mesure["ids"]["proie"]))
    assert int(res.get("total") or 0) > 0, "attaque a degat NUL : %r" % (res,)


def test_cran3_le_NATIF_frappe_la_meme_unite(mesure):
    """Sans ce cran, le cran 2 garderait un accord avec rien : il faut que l'ORACLE frappe aussi,
    et la meme unite. Le natif est rejoue par le montage de `probe_590`."""
    import probe_590_attempted_possession as P590
    m = P590.mesurer(state_name="test_590r8_oracle")
    mm, dispose = m
    try:
        pertes_live = {int(k): int(v) for k, v in
                       P590._pertes(mm["hp"]["live_avant"], mm["hp"]["live_apres"]).items()}
        pertes_port = {int(k): int(v) for k, v in
                       P590._pertes(mm["hp"]["port_avant"], mm["hp"]["port_apres"]).items()}
        proie = int(mm["ids"]["proie"])
        assert proie in pertes_live, (
            "le NATIF n'a pas frappe la proie : pertes=%r -- le montage ne discrimine plus"
            % (pertes_live,))
        assert proie in pertes_port, (
            "le PORT n'a pas frappe la proie : pertes=%r" % (pertes_port,))
        notre_camp = {int(mm["ids"]["caster"]), int(mm["ids"]["allie"])}
        assert not (notre_camp & set(pertes_live)), \
            "le natif a frappe NOTRE camp : l'owner-swap ne serait pas ce qu'on croit"
        assert not (notre_camp & set(pertes_port)), \
            "le port a frappe NOTRE camp -- l'owner-swap du port est faux"
    finally:
        dispose()


def test_cran4_le_montant_natif_est_dans_l_enveloppe_de_tirage_du_port(mesure):
    """LE SEUL ENONCE HONNETE SUR LE MONTANT. Le degat est un TIRAGE : un point de mesure de part
    et d'autre ne peut pas etablir une egalite de formule, et l'exiger ferait rougir un port juste.
    On rejoue donc le cast PORTE avec 40 graines de MT et on demande que la valeur NATIVE tombe
    dans l'enveloppe -- avec la contre-epreuve que l'enveloppe n'est pas degeneree."""
    env = sorted(x for x in (mesure.get("enveloppe") or []) if x)
    assert len(env) >= 30, "enveloppe trop pauvre (%d tirages non nuls) pour conclure" % len(env)
    assert env[0] < env[-1], (
        "enveloppe DEGENEREE (min == max == %d) : le montant ne depend d'aucun tirage, donc ce "
        "cran ne garde rien -- il faudrait alors exiger l'EGALITE avec le natif" % env[0])
    acted = _acted(mesure)
    total_port = int(((acted.get("result") or {}).get("total")) or 0)
    assert env[0] <= total_port <= env[-1], \
        "le tirage du cast (%d) est HORS de sa propre enveloppe [%d, %d]" % (
            total_port, env[0], env[-1])
