"""CLIQUET LIVE #920 -- la relique `MawClawsOfThyrax` (`EffectType` 0x5b5 = 1461
`MawClawsOfThyrax_ExtraCritDmg`).

CRITERE : « le natif ajoute-t-il `extraCritDmg[niveau de RELIQUE] x <unites a trait Summon
ADJACENTES au porteur, TOUS CAMPS CONFONDUS>` au degat de CRIT que ce porteur inflige, et le port
fait-il pareil ? »

Le montage est IMPORTE du probe (`probe_920_maw_claws_of_thyrax_live.py`) au lieu d'etre
re-transcrit : un montage duplique derive de son original sans que rien ne le signale.

TROIS bras, et le deuxieme est celui qui separe cet effet de ses deux voisins de forme :

  1. **AMIS** -- regime nominal : compteur natif == compteur du port, bonus = `extraCritDmg[lvl] x n`,
     salve BIT-EXACTE, et les deux mutants (`NOCHANNEL`, `PASSIF`) MORDENT ;
  2. **ENNEMI** -- les summons passent cote ADVERSE. `DSLSelectors$$AdjacentUnits` =
     `op_Subtraction(Units(AdjacentTiles(origin), unique, sel), origin)` ne filtre AUCUN camp, donc
     le compteur doit RESTER non nul. Un port cale sur `AdjacentFriends` (ce que sont
     `AmuletOfTheVoidwyrm` et `KardiocoreGalvanus`, ses deux voisins de forme) passerait le bras 1
     et tomberait ICI ;
  3. **NEGATIF** (`--trait Hero`) -- compagnons adjacents mais SANS le trait : compteur 0, effet
     publie **INACTIF** (`CreateActiveCondition` = `AmountIsGreaterThanZero(<le compteur>)`, ce qui
     est l'INVERSE de `KardiocoreGalvanus`, dont la condition est `YesTrigger`), canal MUET.

⚠ NON COUVERT ICI, et c'est MESURE, pas oublie : le bras `--porteur-defenseur` du probe (qui isole
`get_OwnerIsCaster` avec un compteur PLEIN). Sur le montage `blackHaarken` -> `tyranTyrantGuard`,
le port rend `+1` par coup PAR RAPPORT AU LIVE, et il le rend AUSSI avec
`scripts/python/engine` ramene a `origin/master` -- donc CE PORT N'Y EST POUR RIEN
(`DELTA [1, 1, 1, 1]` des deux cotes). Residu `#920-r1`. L'etage TRIGGER est garde OFFLINE
(`test_920_maw_claws_of_thyrax_offline.py::test_les_gates_du_bonus_se_TAISENT_chacun_pour_sa_raison`).

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
_PYDIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if _PYDIR not in sys.path:
    sys.path.insert(0, _PYDIR)

import probe_920_maw_claws_of_thyrax_live as P   # noqa: E402  (le FOYER du montage)

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a tout fichier de test live : la cascade des `conftest.py` et le harnais.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/tests/engine/runner/_charge_regime.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/gameconfig.py", "scripts/python/catalog_inject.py",
        "scripts/python/rl_collect_batch.py", "scripts/python/rl_duel.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER : le montage vient du probe, la classe d'effet et son inscription au
        # registre sont l'objet meme du cliquet, le compteur vit dans `components.py`, l'agregateur
        # CRIT dans `damage.py`, et le niveau TERTIAIRE dans `triggers/base.py`.
        "scripts/python/probe_920_maw_claws_of_thyrax_live.py",
        "scripts/python/engine/entities/effects/loki/maw_claws_of_thyrax.py",
        # Le paquet `loki` est traverse par la fermeture d'imports (`factory` l'entre) : declare
        # explicitement, sinon `probe_486r15` rougit sur un DECLENCHEUR trop ETROIT.
        "scripts/python/engine/entities/effects/loki/__init__.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/__init__.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/selectors/accessors.py",
        "scripts/python/engine/entities/formulas.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/runner/operations/damage.py",
        "scripts/python/engine/runner/operations/triggers/base.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Il confronte au natif le canal crit-DEGAT de la relique : le montage (probe), la "
              "classe d'effet et son registre, l'arbre du compteur (selecteurs + formule), le "
              "compteur runner, l'agregateur qui l'appelle et le foyer du niveau TERTIAIRE.",
}


class _Args:
    """Le namespace que `P.build` attend -- meme forme que l'`argparse.Namespace` du probe."""
    seed = "31337"
    board = "MC1_67"
    crit_damage = 2000
    verbose = False

    def __init__(self, trait="Summon", ennemi=False, porteur_defenseur=False):
        self.trait, self.ennemi, self.porteur_defenseur = trait, ennemi, porteur_defenseur


@pytest.fixture(scope="module")
def rpc():
    """Transport RPC + liaison du canal RELIQUE (`snapshot.bind_live_rpc`, #357/#363).

    Sans cette liaison, `UnitContext.tertiary_ability` reste `None` et `triggered_ability_state`
    retombe sur le couple PASSIF (dernier palier) : le bras `PASSIF` ne mordrait plus, et l'accord
    deviendrait DEGENERE."""
    import rl_collect_batch as R
    sid = R._resolve_session()

    def _rpc(method, body=None, timeout=60):
        r = R._rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r.get("result") if isinstance(r, dict) and "result" in r else r

    from engine.runner import snapshot as SNAP
    SNAP.bind_live_rpc(_rpc)
    return _rpc


def _mesure(rpc, n, level, trait="Summon", ennemi=False):
    """Monte, frappe, rejoue -- et rend toutes les vues d'un coup.

    Toute impossibilite de MONTAGE **LEVE** (jamais un skip vert : un echec de montage parti en
    skip est un VERT QUI MENT, #455)."""
    from engine.entities.pathfinding.board import Board
    from _charge_regime import ChargeRegimeHarness
    a = _Args(trait=trait, ennemi=ennemi)
    rid, sf = P.build(a, "test_n%d" % n, level)
    assert rid is not None, "build refuse (n=%d trait=%s ennemi=%s)" % (n, trait, ennemi)
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 90)
        h = ChargeRegimeHarness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
        rec, why = P.stage(h, n, ennemi=ennemi)
        assert rec is not None, "montage impossible (n=%d trait=%s ennemi=%s) : %s" % (
            n, trait, ennemi, why)
        live, why = P.strike(h, rec)
        assert live is not None, "attaque non jouee : %s" % why
        k = len(live)
        off = P.replay(h, rec)[:k]
        vues = {nom: P.replay(h, rec, mutate=nom)[:k] for nom in ("NOCHANNEL", "PASSIF")}
        return rec, live, off, vues, P.etages(h, rec)
    finally:
        from engine.runner.snapshot import clear_ability_states_cache
        clear_ability_states_cache("build#%s" % rid)
        rpc("disposeRunner", {"runnerId": rid}, 20)
        from pathlib import Path
        Path(sf).unlink(missing_ok=True)


def _palier(level):
    return P.paliers_du_gameconfig()[level - 1]


@pytest.mark.parametrize("ennemi", [False, True])
def test_le_bonus_crit_est_le_produit_et_les_SUMMONS_ADVERSES_COMPTENT(rpc, ennemi):
    """Bras 1 (AMIS) et bras 2 (ENNEMI) -- le MEME attendu, et c'est tout le propos.

    `ForAddition(get_OwnerIsCaster, Multiply(ConfigVar(0x42 = extraCritDmg),
    EffectLevel(Effect@+0x38)))`, ou le niveau STOCKE est
    `Count(Unique(UnitsWithTrait(AdjacentUnits(Owner, 1, 3), 0x2 = Summon, 3)))`.

    L'attendu `n_attendu` est CALCULE A LA MAIN par `P.etages` sur le voisinage MESURE (une boucle
    plate contre l'arbre DSL, deux chemins qui doivent coincider) -- jamais deduit du nombre de
    compagnons demande : `genesPrimus`/`genesMagus` SPAWNENT des summons pendant les cycles de tour
    du montage, et les compter serait une attente fausse (mesure #920)."""
    level = 3
    rec, live, off, vues, et = _mesure(rpc, 2, level, ennemi=ennemi)
    n = et["n_attendu"]
    assert n > 0, ("bras POSITIF sans aucun voisin `Summon` mesure -- l'accord y serait DEGENERE "
                   "(voisinage %s)" % (rec["voisins"],))
    assert et["compteur"] == n, "compteur du port %s != %d (%s)" % (et["compteur"], n, et)
    assert rec["actif_natif"] is True, "effet publie INACTIF alors que le compteur vaut %d" % n
    assert rec["niveau_natif"] == n, (
        "compteur NATIF (`decisionView.effects[].level`, tenu egal a `GetCalculateLevel` par "
        "`RefreshEffectsOperation$$UpdateLevel`) = %s, attendu %d" % (rec["niveau_natif"], n))
    assert et["bonus_signe"] == _palier(level) * n, (
        "bonus du port %s != %d x %d" % (et["bonus_signe"], _palier(level), n))
    assert off == live, "port %s != natif %s (etages %s)" % (off, live, et)
    assert vues["NOCHANNEL"] != off, (
        "le canal doit MORDRE (mut=%s off=%s) -- sans quoi l'accord ne prouve rien"
        % (vues["NOCHANNEL"], off))
    assert vues["PASSIF"] != off, (
        "le canal TERTIAIRE doit MORDRE au niveau %d (mut=%s off=%s) : sans lui le port lirait le "
        "niveau des PASSIFS, donc le DERNIER palier" % (level, vues["PASSIF"], off))


def test_sans_le_trait_le_compteur_est_NUL_et_l_effet_est_publie_INACTIF(rpc):
    """Bras 3 (NEGATIF). Les compagnons sont ADJACENTS mais portent `Hero`, pas `Summon`.

    DEUX observables, et le second est PROPRE a cet effet : le compteur tombe a 0, ET l'effet est
    publie `active: false` -- sa `CreateActiveCondition` est `AmountIsGreaterThanZero(<vslot
    +0x5f8> = GetCalculateLevel())`. `KardiocoreGalvanus`, son voisin de forme, resterait ACTIF
    (sa condition est `<DSLTriggers+0x70>` = `YesTrigger`)."""
    rec, live, off, vues, et = _mesure(rpc, 2, 3, trait="Hero")
    assert et["n_attendu"] == 0, "montage rate : %s voisin(s) Summon" % (et["voisins_summon"],)
    assert et["compteur"] == 0
    assert rec["actif_natif"] is False, (
        "l'effet est publie ACTIF a compteur nul -- REFUTATION de la RE (`CreateActiveCondition` "
        "= `AmountIsGreaterThanZero`), pas un montage rate")
    assert et["effet_actif_port"] is False
    assert et["bonus_signe"] is None
    assert off == live, "port %s != natif %s (etages %s)" % (off, live, et)
    assert vues["NOCHANNEL"] == off, (
        "le canal est deja MUET : retirer la classe ne peut RIEN changer (mut=%s off=%s)"
        % (vues["NOCHANNEL"], off))
