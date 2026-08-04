"""#579-r1 -- la disposition d'un `Nullable<T>` ne se CODE PAS EN DUR dans `readAbilityState`.

CE QUE CE FICHIER GARDE, et pourquoi il est OFFLINE et au niveau du SOURCE
--------------------------------------------------------------------------

Le defaut vit dans `frida/hooks/features/ai-step/internals.ts`, c'est-a-dire dans du code qui
tourne DANS Frida : aucun test Python ne peut l'executer, et aucun test live ne peut le voir tant
que le bundle deploye ne porte pas le correctif. Ce qu'un garde-fou cote depot PEUT tenir, c'est
qu'on ne re-code pas la convention en dur -- et c'est exactement ce qui avait produit le defaut.

LE DEFAUT, MESURE (2026-08-04, session 3, build `rnca9r7q6c`). `readAbilityState` lisait les
`Nullable<T>` de `IdunBattle.Entities.Components.ActiveAbility` a la disposition
`{ int value @+0 ; bool hasValue @+4 }`. DEUX casts dans la MEME bataille, a
`IdunBattle.Entities.Components.TurnComponent$$GetAmountOfTurnsEnded` = **6** puis **19**,
publiaient tous deux `unresetedLastTurnUsed = 1`. Or
`IdunBattle.Operations.SetActiveAbilityUsedOperation$$Execute` ecrit
`Nullable(GetAmountOfTurnsEnded(GetMatchTurn(state), 0))` dans ce champ, et ce compteur est
`Sum(dict@+0x40.Values) + turnsToAdd`, donc MONOTONE : les deux valeurs stockees ne peuvent pas
etre toutes deux `1`. Le `1` publie etait le bit `hasValue`.

`System.Nullable`1` declare `hasValue` PUIS `value` -- lu par `classFields("System",
"Nullable`1")`, et confirme au decompile : `IdunBattle.Core.Services.AttackQuery$$IsAlreadyUsedThisTurn`
comme `IdunBattle.Entities.Components.ActiveAbility$$get_IsInCooldown` prennent l'octet `HasValue`
sur `fields[0]`.

RAYON DE SOUFFLE, dans le MEME foyer : `cooldown` et `ammoCost` etaient lus a la meme convention
inverse. `cooldown` valait donc `1` pour TOUT cooldown non nul, ce qui rendait
`engine/runner/operations/ability_reset.py` (`remaining_cooldown > 1`, mirror d'
`IdunBattle.Core.Services.BattleQuery$$EntityCanHaveActiveAbilityReset`) STRUCTURELLEMENT faux.
Les predicats de PRESENCE, eux, coincidaient par accident (`value & 0xff != 0` equivaut a
`HasValue && Value > 0` tant que la valeur tient sur un octet non nul) -- c'est ce qui explique
qu'aucun test ne l'ait jamais vu.

⚠ Ce cran ne dit RIEN de la justesse du capteur en vol : il dit que la disposition est RESOLUE et
non SUPPOSEE. La confrontation live, elle, est `scripts/python/probe_579_nullable_layout.py`, et
elle exige une fenetre de reinject.

ASCII only.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

#: `scripts/python/tests/` -> racine du depot.
_ROOT = Path(__file__).resolve().parents[3]
_INTERNALS = _ROOT / "frida" / "hooks" / "features" / "ai-step" / "internals.ts"


@pytest.fixture(scope="module")
def source() -> str:
    if not _INTERNALS.exists():
        pytest.fail("source introuvable : %s -- le chemin du hook a bouge, ce cran est aveugle"
                    % _INTERNALS, pytrace=False)
    return _INTERNALS.read_text(encoding="utf-8")


def test_la_disposition_du_nullable_est_resolue_par_reflexion(source):
    """Le foyer doit DERIVER `hasValue`/`value` des metadonnees, pas les poser."""
    assert "nullableLayoutOf" in source, (
        "`nullableLayoutOf` a disparu de `internals.ts` : la disposition interne des `Nullable<T>` "
        "est redevenue une convention posee a la main. C'est exactement le defaut #579-r1.")
    assert re.search(r'getFieldOffset\(\s*k\s*,\s*"hasValue"\s*\)', source), (
        "la resolution de `hasValue` PAR NOM sur la classe `Nullable`1` a disparu. Le patron de "
        "reference est `game/match-state.ts` (`UnitComponent.DeathReason`).")
    assert re.search(r'getFieldOffset\(\s*k\s*,\s*"value"\s*\)', source), (
        "la resolution de `value` PAR NOM a disparu -- meme motif.")


def test_aucun_offset_interne_de_nullable_code_en_dur(source):
    """Aucune lecture de `Nullable` a un offset interne LITTERAL dans ce fichier.

    Les trois formes du defaut, telles qu'elles existaient : `base.add(off + 4).readU8()` pour le
    `hasValue` d'un `Nullable<int>`, `ab.add(<champ>Off + 4).readU8()` pour `cooldown`/`ammoCost`,
    et `ab.add(abOverrideStateOff + 0xc).readU8()` pour le `Nullable<AbilityState>`."""
    offenders = re.findall(r"\.add\([^)]*?\+\s*(?:4|0x4|0xc|12)\s*\)\.readU8\(\)", source)
    assert not offenders, (
        "lecture(s) de `hasValue` a un offset interne LITTERAL : %r. La disposition de "
        "`System.Nullable`1` est `{ bool hasValue @+0 ; T value @+4 }` -- MESUREE, pas supposee "
        "(#579-r1) -- et elle doit se DERIVER (`nullableLayoutOf`), sinon le prochain build ou le "
        "prochain type de valeur la casse en silence." % offenders)


def test_la_convention_inverse_n_est_plus_documentee(source):
    """La prose comptait autant que le code : c'est elle qui a fait ecrire « LUE, pas supposee »."""
    bad = re.search(r"\{\s*int value @\+0\s*;\s*bool hasValue @\+4\s*\}", source)
    assert bad is None, (
        "`internals.ts` documente encore la disposition INVERSE `{ int value @+0 ; bool hasValue "
        "@+4 }`. Elle est REFUTEE par la mesure (#579-r1) : deux casts a `GetAmountOfTurnsEnded` "
        "6 et 19 publiaient tous deux `1`.")


def test_le_layout_resolu_est_publie(source):
    """Un capteur qui ne dit pas ce qu'il a resolu laisse un `null` de panne indiscernable d'un
    `null` de mesure -- et c'est ce qui a permis au defaut de passer pour un vert."""
    assert "nullableLayout" in source, (
        "`abilityStateLayout()` ne publie plus la disposition resolue. Sans elle, la fenetre de "
        "reinject ne peut pas confronter ce que le capteur a lu.")
