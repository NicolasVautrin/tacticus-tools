"""#443-r2-b1 -- la face DECISION seede son `EffectsState` par la MEME porte que la face COMBAT.

100 % OFFLINE : aucun runner, aucun RPC. Le montage LIVE qui a chiffre l'ecart (-35 points
d'utilite de paire, poids BC `SUPPRESSIVEFIRE_TargetWithOverwatch`) vit dans
`test_443r2_only_active_overwatch_live.py` ; ici on garde le MECANISME, la ou il ne coute rien.

CE QUE CE FICHIER GARDE, et pourquoi chaque assertion est SEULE a le voir :

  [A] le canal STRUCTURE (`EffectsState`) voit l'instance INERTE -- c'est LE fix. Sans lui, tout
      mirror d'un `HasEffect(..., onlyActive = 0)` rend FAUX la ou le natif rend VRAI, en silence.
  [B] l'instance inerte ne CONTRIBUE a rien : `active_effects` conjugue le flag
      `EffectComponent.IsActive @+0x5c` et la `CreateActiveCondition` portee. Sans cette assertion,
      le fix pourrait faire entrer l'inerte dans des NOMBRES -- une regression bien plus grave que
      le trou qu'il ferme.
  [C] la liste BRUTE reste ACTIF-ONLY : les lecteurs qui n'ont pas de flag a consulter
      (`battle_query.can_use_ability`, `entity_has_effect`, les feuilles de tuile...) gardent
      EXACTEMENT leur verdict d'avant la bascule. C'est le pendant de `snapshot._effect_names`.
  [D] la projection est l'IDENTITE sur un payload du canal NU : les centaines de probes et de tests
      qui captent nu ne doivent RIEN voir bouger.
  [E] les DEUX seams d'`ai/context.py` projettent -- [C] ne teste que `step_context`.
  [F] tout consommateur de PRODUCTION qui capte lui-meme un `decisionView` passe par la porte.
      C'est le SEUL cran qui garde notre propre cadence : un nouveau consommateur repart par
      defaut sur le canal nu, sans erreur ni crash.

Les six crans ont ete CONTRE-EPROUVES un par un (mutation -> rouge -> restauration -> vert) :
6/6 mordent. ⚠ [F] ne mordait PAS dans sa premiere forme (`"decision_view_seed_body" in src`) :
le COMMENTAIRE qui explique la porte contient son nom, donc retirer l'APPEL laissait le cran vert.
Il lit desormais l'AST -- une prose ne peut plus le desarmer.

Probe jumeau (avec l'inventaire DERIVE des lecteurs) :
`scripts/python/probe_443r2b1_decision_inactive_readers.py --inventory`. ASCII only.
"""
from __future__ import annotations

import pytest

import probe_443r2b1_decision_inactive_readers as P


@pytest.fixture(scope="module")
def crans():
    return {titre: (ok, detail) for titre, ok, detail in P.mesure()}


@pytest.mark.parametrize("cran", [c.split("]")[0] + "]" for c in
                                  ("[A]", "[B]", "[C]", "[D]", "[E]", "[F]")])
def test_le_cran_est_vert(crans, cran):
    """Un test par cran : un echec NOMME celui qui a lache, au lieu d'un booleen global."""
    lot = {t: v for t, v in crans.items() if t.startswith(cran)}
    assert lot, f"cran {cran} ABSENT du probe -- la garde a ete deplacee sans etre remplacee"
    for titre, (ok, detail) in lot.items():
        assert ok, f"{titre} -- {detail}"


def test_les_lecteurs_du_substrat_DECISION_sont_derivables():
    """L'inventaire se DERIVE du code executable, il ne se saisit pas. Un zero ici voudrait dire
    que la derivation est cassee (import, AST, arborescence) -- pas qu'il n'y a plus de lecteur."""
    rows = P.inventory()
    struct = [r for r in rows if (r["eff_state"] or r["foyer"]) and not r["seam"]
              and r["face"] in ("DECISION", "PARTAGE")]
    presence = [r for r in struct if r["presence"]]
    assert len(struct) >= 15, (
        "la derivation des lecteurs du substrat DECISION rend %d entrees -- elle est cassee "
        "(elle en trouvait 19 au portage de #443-r2-b1)" % len(struct))
    assert presence, "aucun lecteur PRESENCE derive : le classement PRESENCE/ACTIVITE est mort"
    # Le foyer NOMME du predicat `HasEffect(..., onlyActive = 0)` DOIT y etre : c'est lui que la
    # mesure de #501 a pris en flagrant delit.
    noms = {(r["file"], r["fn"]) for r in presence}
    assert ("engine/battle_query.py", "scene_has_effect") in noms, (
        "`battle_query.scene_has_effect` -- le foyer du predicat mesure a -35 -- n'est plus "
        "derive comme lecteur PRESENCE : %s" % sorted(noms))
