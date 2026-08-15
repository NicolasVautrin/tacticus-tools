"""#1013-r3 (+ #590-r5) -- ce qu'un `customUtility` de call-site PEUT faire, et ce qu'il ne peut PAS.

LE FAIT NATIF, lu sur `t6dpr4k06g`. Un `customUtility` (une `UtilityDefinition` construite AU SITE
par un noeud `PerformAIAttack` / `PerformAIAbility`) descend jusqu'a
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`
(chaine : `ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext` -> slot 7 du
playbook -> `ComparablePlaybooku003C...u003E$$EvaluateInternal` -> ce corps). Il n'y est **JAMAIS
somme au score**. TROIS issues, et trois seulement :

    r == BaseUtility.statics+0x18 ou +0x20 (= Fix64.MinValue)  -> Nullable VIDE (aucune action)
    r == BaseUtility.statics+0x10          (= Fix64.MaxValue)  -> utilite = MaxValue
    sinon                                                      -> chemin NORMAL, r est JETEE

CE QUE CE FICHIER GARDE. Deux verdicts reposent sur cette lecture, et ils reposent sur des DONNEES
qui peuvent bouger sous eux sans que personne ne le voie :

  * `#1013-r3` -- FERME PAR REFUTATION. `TheArdentBlade_GeminaeUtility` yield `0` ou
    `+GetUtilityValue("LikesAdjacentCelestine")`. Tant que ce poids est un nombre FINI, la somme du
    bucket n'est aucune des trois sentinelles, donc le natif prend le chemin normal -- c'est-a-dire
    exactement ce que fait le port, qui n'expose pas le parametre. Si le poids disparaissait du seed
    ou devenait une valeur extreme, la refutation tomberait : c'est ce que garde l'etage 1.
  * `#590-r5` -- TRANCHE. `OnlyCertainTargetUtility` yield `statics+0x20` = MinValue hors liste et
    `statics+0x00` = 0 dans la liste : ELIMINATION / scoring normal. Le port l'exprime par
    `allowed_targets`, un ensemble d'ids -- PAS un score. L'etage 2 garde ce contrat, parce qu'un
    port qui glisserait vers un bonus numerique reintroduirait exactement le regime que le
    decompile exclut.

Aucune valeur de gameplay n'est ecrite en dur : le poids est RE-DERIVE du seed. ASCII only.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

DECLENCHEUR = {
    # PERIMETRE LARGE et MESURE : ce fichier importe le registre d'abilities (via la feuille
    # `PerformAIAbility`) et lit le seed BC. Declarer etroit produirait un FAUX VERT.
    # Les DEUX formes sont necessaires : `**/` exige un SEGMENT.
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py", "data/seed-bc.json"),
    # `build: False` : rien n'est fige DEPUIS le binaire ici -- ce sont la DONNEE du seed et le
    # CONTRAT du port qui sont gardes. La lecture du decompile, elle, vit en prose (decider.py).
    "build": False,
    "toujours": True,
    "raison": "Garde les deux verdicts qui reposent sur la lecture des sentinelles de BaseUtility : "
              "la refutation de #1013-r3 (le poids reste un nombre fini) et le contrat "
              "d'ELIMINATION de #590-r5 (allowed_targets est un ensemble d'ids, pas un score).",
}

#: `tests/engine/<ce fichier>` -> parents : [0] engine, [1] tests, [2] python, [3] scripts,
#: [4] racine du depot. `data/` est VERSIONNE a la racine (entree LUE, jamais ecrite).
_SEED = Path(__file__).resolve().parents[4] / "data" / "seed-bc.json"


def _poids_utilite(groupe: str, cle: str):
    """Le poids `BC.Utilities.Default.<groupe>.<cle>`, RE-DERIVE -- jamais recopie."""
    if not _SEED.exists():
        pytest.fail("seed BC introuvable (%s) : montage KO, jamais un skip" % (_SEED,))
    d = json.loads(_SEED.read_text(encoding="utf-8"))
    return ((d.get("Utilities") or {}).get("Default") or {}).get(groupe, {}).get(cle)


def test_etage1_le_poids_de_l_utilite_66_est_un_NOMBRE_FINI():
    """La refutation de #1013-r3 tient PARCE QUE la valeur yieldee n'est pas une sentinelle.

    `TheArdentBlade_GeminaeUtility` yield `Fix64(0)` ou `Fix64(0) + GetUtilityValue(
    "LikesAdjacentCelestine")`. Les trois sentinelles TESTEES par `CalculateActionUtility` sont
    `Fix64.MinValue`, `Fix64.MinValue/(1+1e-6)` et `Fix64.MaxValue` (bornes d'un entier 64 bits en
    virgule fixe Q31.32). Un poids fini les manque toutes."""
    from engine.utilities.utility_type import UtilityType
    poids = _poids_utilite(UtilityType.TheArdentBlade_Geminae.name, "LikesAdjacentCelestine")
    assert poids is not None, (
        "`Utilities.Default.%s.LikesAdjacentCelestine` a DISPARU du seed : la refutation de "
        "#1013-r3 citait cette valeur, il faut la RE-LIRE avant de s'y fier"
        % UtilityType.TheArdentBlade_Geminae.name)
    val = float(poids)
    # Bornes Fix64 (Q31.32) : |valeur| < 2**31. Un poids de BC vit trois ordres de grandeur en
    # dessous ; ce cran n'est pas un seuil ajuste, c'est la borne du TYPE.
    assert abs(val) < 2 ** 31, (
        "poids %r hors des bornes Fix64 : il pourrait alors coincider avec une sentinelle et la "
        "refutation de #1013-r3 tomberait" % (poids,))
    assert val != 0, ("un poids NUL rendrait ce cran vacant (l'utilite serait plate des deux "
                      "cotes) -- le montage doit rester discriminant")


def test_etage2_le_customUtility_du_port_est_une_EXCLUSION_pas_un_score():
    """#590-r5. Le contrat porte est `(state, actor_id[, utility_entity_id]) -> set[int] | None`,
    materialisation de `OnlyCertainTargetUtility` -> Nullable VIDE hors liste.

    Un port qui glisserait vers un bonus numerique reintroduirait le regime que le decompile
    EXCLUT : `CalculateActionUtility` jette toute valeur qui n'est pas une des trois sentinelles."""
    from engine.runner.abilities.behaviours.ai_control import PerformAIAbility
    from engine.runner.abilities.loki.attempted_possession import (
        attempted_possession_custom_utility)

    # Le consommateur reel de 1101 rend bien un ENSEMBLE d'ids (ou None), jamais un nombre.
    fn = attempted_possession_custom_utility(None, 77)
    sig = inspect.signature(fn)
    assert len(sig.parameters) == 3, (
        "le `custom_utility` de 1101 doit declarer TROIS parametres pour recevoir le canal "
        "`utilityEntity` (#590-r4) ; il en declare %d" % len(sig.parameters))
    assert PerformAIAbility._accepte_utility_entity(fn) is True

    # Et la feuille le PROPAGE en `allowed_targets`, jamais en terme d'utilite : le corps du
    # behaviour ne connait aucun canal de score.
    src = inspect.getsource(PerformAIAbility.execute)
    assert "allowed_targets=allowed" in src, (
        "la feuille ne propage plus le `customUtility` en `allowed_targets` -- si le port a "
        "acquis un canal de SCORE, il faut RE-LIRE `CalculateActionUtility` avant de l'emprunter")
    assert "custom_utility" in src


def test_etage3_un_custom_utility_qui_rend_None_ne_contraint_RIEN():
    """`GetAttackCustomUtility` rend `null` quand `GetPreferredAttackTarget` ne trouve rien -> le
    natif ne fabrique AUCUNE `UtilityDefinition`, donc `CalculateActionUtility` prend le chemin
    normal des sa premiere ligne (`customUtility == null`). Le port doit faire pareil : `None` =
    aucune contrainte, PAS un ensemble vide (qui, lui, interdirait toute cible)."""
    from engine.runner.abilities.loki.attempted_possession import (
        attempted_possession_custom_utility)
    import engine.runner.abilities.loki.attempted_possession as AP

    class _EtatVide:
        def get_entity(self, _uid):
            return None

    fn = attempted_possession_custom_utility(_EtatVide(), 77)
    assert fn(_EtatVide(), 81, 77) is None, (
        "aucune cible preferee doit rendre `None` (aucune contrainte), jamais `set()` -- un "
        "ensemble vide interdirait TOUTE cible, l'inverse du natif")
    assert AP.attempted_possession_preferred_target(_EtatVide(), 77, 81) is None
