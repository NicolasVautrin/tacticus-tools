"""#957-r3 -- `1197 ExcruciatingFrequencies` : `nrOfHits` LITTERAL, PAS `GetDefaultAttackHits`.

`IdunBattle.AI.Playbook.Loki.ExcruciatingFrequenciesPlaybook$$MakeDamagePredictions` passe
`IdunBattle.Entities.Abilities.AActiveAbility$$GetHits()` = `GetNumberConstant(0x2f = nrOfHits)`
**BRUT** au 7e argument de
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`.
Le chemin GENERIQUE du port passait par `AActiveAbility.get_special_hits` =
`GetDefaultAttackHits(nrOfHits, ExtraHits[, Melee])`, qui AJOUTE la stat `ExtraHits` du caster --
que ce playbook n'ajoute pas.

⚠ **LES DEUX COINCIDENT TANT QU'`ExtraHits = 0`**, et c'est tout le probleme : rien ne le signalait.
Ce fichier rend donc l'ecart VISIBLE en posant `ExtraHits != 0` -- sans quoi il garderait un accord
en regime DEGENERE.

CE QU'IL GARDE (offline pur) :

  1. **L'ENTREE DE REGISTRE EXISTE** -- 1197 est dans `_MAKE_DMG_INPUT_OVERRIDES`, et son handler
     rend bien une cle `hits_override`.
  2. **LA VALEUR EST LE LITTERAL DE CONFIG** -- `hits_override == constants["nrOfHits"]`.
  3. **LE REGIME EST DISCRIMINANT** -- avec `ExtraHits = 2`, le chemin generique
     (`get_special_hits`) rend une valeur DIFFERENTE de l'override. Sans ce cran, un accord ne
     prouverait rien.
  4. **LA SOURCE EST LA BONNE** -- `nrOfHits` est lu dans les CONSTANTES (`GetNumberConstant`),
     comme `_stikkbomb_inputs`, pas dans les variables par niveau.

⚠ NON CONFRONTE LIVE : ce fichier garde la FORME de l'override, pas l'accord avec le natif sur un
porteur reel (`emperNoiseMarine` avec un `+ExtraHits`). Cf. le rapport de tranche.

ASCII only. Point d'entree : `docs/rl/case-957-six-faces-decision-lot2.md` SS7.
"""
from __future__ import annotations

import gameconfig as GC
from engine.entities.abilities.ability_configuration import AbilityConfiguration
from engine.entities.active_ability_type import ActiveAbilityType
from engine.playbook.prediction.abilities import (_MAKE_DMG_INPUT_OVERRIDES,
                                                  _excruciating_frequencies_inputs)
from engine.entities.stats import StatType
from engine.services.attack_hits_formula import get_default_attack_hits

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/playbook/prediction/abilities.py",
        "scripts/python/engine/playbook/excruciating_frequencies.py",
        "scripts/python/engine/entities/abilities/active_ability.py",
        "scripts/python/engine/services/attack_hits_formula.py",
        "scripts/python/gameconfig.py"),
    "build": True,
    "toujours": False,
    "raison": "Il garde le `hits_override` LITTERAL de 1197 (le playbook natif ne passe pas par "
              "`GetDefaultAttackHits`) et le regime qui le rend discriminant.",
}

_NOM = "ExcruciatingFrequencies"


def _cfg():
    return AbilityConfiguration.from_gameconfig(_NOM, GC.ability(_NOM))


def test_l_entree_de_registre_existe():
    """(1) Sans elle, `make_damage_predictions` retombe sur le chemin generique et l'override est
    lettre morte -- la route BESPOKE de 1197 (`playbook/excruciating_frequencies.py`) appelle
    `make_damage_predictions`, donc elle traverse CE registre."""
    assert ActiveAbilityType.ExcruciatingFrequencies in _MAKE_DMG_INPUT_OVERRIDES, (
        "1197 `ExcruciatingFrequencies` n'est pas dans `_MAKE_DMG_INPUT_OVERRIDES` -- le chemin "
        "generique ajouterait la stat `ExtraHits` du caster, que le playbook natif n'ajoute pas")
    assert (_MAKE_DMG_INPUT_OVERRIDES[ActiveAbilityType.ExcruciatingFrequencies]
            is _excruciating_frequencies_inputs), "le handler de 1197 n'est pas le sien"


def test_l_override_vaut_le_litteral_de_config():
    """(2) et (4) La valeur, et sa SOURCE : `GetNumberConstant(0x2f)` lit les CONSTANTES."""
    cfg = _cfg()
    assert cfg is not None, f"`{_NOM}` absent du gameconfig -- le montage n'a rien a mesurer"
    n = int((cfg.constants or {}).get("nrOfHits") or 0)
    assert n >= 1, (f"`nrOfHits` vaut {n} dans les CONSTANTES de `{_NOM}` -- s'il avait migre vers "
                    f"les variables, l'override rendrait `{{}}` en silence")
    out = _excruciating_frequencies_inputs(None, None, None, None, cfg)
    assert out.get("hits_override") == n, (
        f"`hits_override` = {out.get('hits_override')}, attendu le litteral de config {n}")
    assert "base_override" not in out and "profile_override" not in out, (
        f"le handler surcharge autre chose que les HITS ({sorted(out)}) -- le call-site natif passe "
        f"`BlightGrenadesAbility$$GetDamageFormula` (= le generique) et `GetDamageProfile(config)`")


def test_le_regime_est_discriminant_avec_extrahits():
    """(3) NON-TRIVIALITE. Le chemin GENERIQUE (`get_default_attack_hits`, ce qu'appelle
    `AActiveAbility.get_special_hits`) DOIT rendre une valeur DIFFERENTE de l'override des que le
    caster porte un `+ExtraHits`. Sinon les crans 1/2 gardent une forme sans effet mesurable."""
    n = int((_cfg().constants or {}).get("nrOfHits") or 0)
    generique = get_default_attack_hits(n, 2, 0, is_melee=False)
    assert generique != n, (
        f"avec `ExtraHits = 2`, le chemin generique rend {generique} et l'override {n} : ils "
        f"COINCIDENT, donc l'override ne change RIEN et ce fichier ne discriminerait rien. "
        f"(`StatType.EXTRA_HITS` = {int(StatType.EXTRA_HITS)})")
    assert get_default_attack_hits(n, 0, 0, is_melee=False) == n, (
        "sans `ExtraHits`, le generique DOIT deja valoir l'override -- c'est ce qui explique que "
        "l'ecart soit reste invisible, et le cran qui le documente")
