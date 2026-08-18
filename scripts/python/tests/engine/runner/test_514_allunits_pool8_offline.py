"""#514 -- GARDE offline des DEUX primitives d'ensemble d'unites.

Le probe `probe_514_allunits_rayon_de_souffle.py` MESURE (rayon de souffle, contrefactuels) ; ce
fichier GARDE. Ce qu'il fige, et pourquoi chaque cran existe :

  1. `AllUnits` ne filtre PAS, `AllAliveUnits` filtre. Les deux corps natifs
     (`BattleQuery$$GetAllUnits` / `$$GetAllAliveUnits`) sont IDENTIQUES a l'ordinal d'`EntityPool`
     pres (`8` / `0`) : une inversion serait MUETTE cote natif comme cote port.
  2. L'ATTRIBUTION site par site : tout site executable qui ecrit `AllUnits(` doit etre declare
     avec le symbole natif pool-8 qui le justifie. C'est le seul cran qui empeche un futur port
     d'ecrire `AllUnits()` par habitude la ou le natif passe le champ partage `<dsl>+0x20` -- la
     degradation serait PERMISSIVE (un cadavre entre dans un `Enemies`/`Friends`) et donc
     silencieuse.
  3. `LeadingTheCharge$$GetExtraPierceRatio` COMPTE bien un cadavre allie. Avant #514 ce compte
     etait structurellement NUL : mesure live du 2026-08-07 (`probe_514_extra_pierce_cadavres.py`,
     board MC1_67, un allie mort, armure de cible 2400) -- port d'AVANT #514
     `[970, 1119, 900]` contre natif `[1212, 1399, 1125]`, soit **-20 %** de degat sur la charge.
"""
from __future__ import annotations

import os
import sys

import pytest

_PYDIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PYDIR not in sys.path:
    sys.path.insert(0, _PYDIR)

import probe_514_allunits_rayon_de_souffle as P514      # noqa: E402
from engine.dsl.base import DslContext                  # noqa: E402
from engine.entities.selectors.tiles import AllAliveUnits, AllUnits  # noqa: E402


DECLENCHEUR = {
    # PERIMETRE LARGE, et c'est MESURE, pas prudentiel : le cran 2 de ce fichier delegue au
    # cliquet d'attribution de `probe_514_allunits_rayon_de_souffle.py`, dont l'inventaire AST
    # visite TOUT `scripts/python/**`. N'importe quel fichier qui se met a ecrire `AllUnits(`
    # change donc le verdict, meme sans toucher au moteur ni a ce test.
    # ⚠ Les DEUX formes sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py`
    # ne voit PAS `scripts/python/board.py`.
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py"),
    "build": True,
    "toujours": False,
    "raison": "L'ATTRIBUTION de chaque site pool-8 est adossee a un symbole natif "
              "(`WaaaghAbility$$GetAttackBehaviour`, `LeadingTheChargeAbility$$GetExtraPierceRatio`) "
              "et a l'ordinal d'`IdunBattle.Entities.Enum.EntityPool` : un changement de build peut "
              "deplacer un call-site d'un pool a l'autre sans qu'une ligne du port bouge. Les deux "
              "corps natifs ne different QUE par cet ordinal, donc l'inversion serait MUETTE.",
}


def _unites():
    return [
        {"id": 1, "team": 1, "player": 1, "alive": True, "hp": 100,
         "pos": {"col": 3, "row": 3}, "visualId": "ami", "_traits": set()},
        {"id": 2, "team": 1, "player": 1, "alive": False, "hp": 0,
         "pos": {"col": 3, "row": 4}, "visualId": "cadavre_ami", "_traits": set()},
        {"id": 3, "team": 2, "player": 2, "alive": True, "hp": 100,
         "pos": {"col": 4, "row": 3}, "visualId": "ennemi", "_traits": set()},
    ]


def _ctx():
    u = _unites()
    return DslContext(units=u, caster=u[0], target=u[2],
                      has_trait=lambda x, t: False, has_unit_flag=lambda x, f: False,
                      faction_of=lambda x: None)


def test_allunits_est_le_pool_8_et_ne_filtre_pas_les_mortes():
    """`DSLSelectors$$AllUnits` -> `AllUnitsSelector$$Select` -> IBattleQuery slot 136
    `GetAllUnits` -> `state.GetPool(EntityPool.AllUnits)` : AUCUN predicat de vie dans le corps."""
    got = [u["id"] for u in AllUnits().select(_ctx())]
    assert got == [1, 2, 3], got


def test_allaliveunits_est_le_pool_0_et_filtre_les_mortes():
    """Le champ PARTAGE `<DSLSelectors>+0x20` -> `AllAliveUnitsSelector$$Select` -> slot 137
    `GetAllAliveUnits` -> `state.GetPool(EntityPool.AliveUnits)`."""
    got = [u["id"] for u in AllAliveUnits().select(_ctx())]
    assert got == [1, 3], got


def test_les_deux_primitives_divergent_des_qu_il_y_a_UN_cadavre():
    """Cran anti-regime-DEGENERE : sans cadavre les deux rendraient la meme chose, et ce fichier
    passerait sur un port casse."""
    ctx = _ctx()
    tous = [u["id"] for u in AllUnits().select(ctx)]
    vivants = [u["id"] for u in AllAliveUnits().select(ctx)]
    assert tous != vivants, "montage DEGENERE : aucun cadavre, la garde ne prouve rien"


def test_chaque_site_de_AllUnits_est_ATTRIBUE_a_un_natif_pool8():
    """Cliquet d'attribution -- l'inventaire est DERIVE par AST, jamais ecrit a la main."""
    fails: list = []
    trouve = P514.etape_1(fails)
    assert not fails, fails
    non_declares = [(f, p, l) for (f, p, l) in trouve["AllUnits"]
                    if (f, p) not in P514.SITES_POOL8]
    assert not non_declares, (
        "sites `AllUnits(` non declares dans SITES_POOL8 : %r. `AllUnits` = pool 8 = MORTS INCLUS ; "
        "si le natif du site passe `<dsl>+0x20`, ecrire `AllAliveUnits(`." % (non_declares,))
    vus = {(f, p) for (f, p, _l) in trouve["AllUnits"]}
    perimes = sorted(set(P514.SITES_POOL8) - vus)
    assert not perimes, "declarations PERIMEES dans SITES_POOL8 : %r" % (perimes,)


def test_chaque_attribution_cite_un_call_site_du_releve_natif():
    """Cran 3b (#1084) -- L'ATTRIBUTION N'EST PAS UNE PROSE LIBRE.

    Le cran precedent exige qu'un site `AllUnits(` soit DECLARE ; il ne dit rien de ce que la
    declaration CITE. Un symbole plausible mais qui n'appelle pas `DSLSelectors$$AllUnits` rendait
    donc le cliquet vert sur une justification INVENTEE -- pire que l'absence, parce qu'elle a
    l'air lue. On confronte ici chaque symbole au releve `list_xrefs` du build."""
    hors = sorted((cle, sym) for cle, sym in P514.SITES_POOL8.items()
                  if not (sym.startswith("<") and sym.endswith(">"))
                  and sym not in P514.CALL_SITES_NATIFS_POOL8)
    assert not hors, (
        "attribution(s) citant un symbole absent du releve des call-sites natifs pool-8 : %r" % (hors,))
    # ANTI-VACUITE : un releve vide, ou une table qui ne contiendrait QUE des auto-tests, rendrait
    # l'assertion ci-dessus vraie sans rien mesurer.
    reels = [s for s in P514.SITES_POOL8.values() if not s.startswith("<")]
    assert len(reels) >= 6 and len(P514.CALL_SITES_NATIFS_POOL8) >= 20, (
        len(reels), len(P514.CALL_SITES_NATIFS_POOL8))


def test_MUTATION_un_symbole_INVENTE_fait_rougir_le_cran_3b(monkeypatch):
    """Contre-epreuve du cran precedent : il doit MORDRE.

    On declare un site avec un symbole PLAUSIBLE (meme namespace, meme forme `$$Methode`) qui
    n'appelle pas `DSLSelectors$$AllUnits`. Sans le cran 3b, l'etape 3 le trouverait << declare >>
    et passerait -- c'est le regime ou une attribution INVENTEE ressemble a une attribution LUE."""
    faux = dict(P514.SITES_POOL8)
    faux[("engine/runner/abilities/orks.py", "waaagh_attack_tree")] = (
        "IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetInexistantBehaviour")
    monkeypatch.setattr(P514, "SITES_POOL8", faux)
    hors = [(cle, sym) for cle, sym in P514.SITES_POOL8.items()
            if not (sym.startswith("<") and sym.endswith(">"))
            and sym not in P514.CALL_SITES_NATIFS_POOL8]
    assert hors, ("un symbole INVENTE ne fait pas rougir le cran 3b : la table d'attribution "
                  "redevient une prose libre")


def test_le_port_utilise_bien_AllAliveUnits_partout_ailleurs():
    """Le pendant du cran precedent : le gros du port DOIT passer par la primitive ALIVE. Un zero
    ici signifierait que l'inventaire ne visite plus rien -- un recenseur qui ne visite pas ne peut
    pas rendre zero pour la bonne raison."""
    fails: list = []
    trouve = P514.etape_1(fails)
    assert not fails, fails
    sous_engine = [s for s in trouve["AllAliveUnits"] if s[0].startswith("engine/")]
    assert len(sous_engine) >= 7, sous_engine


def test_extra_pierce_de_leading_the_charge_compte_un_cadavre_allie():
    """`Count(Filter(AllUnits(), IsNormalUnit & AreFriends(Owner) & HasBeenDefeated))` -- avant
    #514 ce compte etait structurellement NUL (source filtrante sur un predicat de MORT)."""
    from engine.runner.abilities.loki.leading_the_charge import (
        leading_the_charge_defeated_friends_selector)
    ctx = _ctx()
    got = [u["id"] for u in leading_the_charge_defeated_friends_selector().evaluate(ctx)]
    assert got == [2], got          # l'ALLIE mort ; ni le vivant, ni l'ennemi


@pytest.mark.parametrize("nom", ["AllUnits", "AllAliveUnits"])
def test_les_deux_primitives_sont_exportees_par_le_paquet(nom):
    """Un mirror neuf qui n'est pas exporte se contourne par un import direct, et la prochaine
    tranche recopie le contournement."""
    import engine.entities.selectors as S
    assert hasattr(S, nom), nom
    assert nom in getattr(S, "__all__", ()), nom
