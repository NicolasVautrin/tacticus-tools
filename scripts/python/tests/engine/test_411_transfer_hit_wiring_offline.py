"""#411 -- GARDE DE CABLAGE de `DealDamageInfo[+0x1D]` (le block GARANTI, 0 tirage).

Ce que verrouille ce fichier, et POURQUOI il est OFFLINE : les faits de RE qui rendent le residu
`+0x1D` de `case-407` §7 ACTIONNABLE se perissent en silence. Trois d'entre eux sont des DONNEES
(ids d'enum, porteurs, voie de montage) et le quatrieme est un INVARIANT DE PORT (si la mecanique
entre au registre, la route de garantie doit entrer avec elle).

RE (detail : `docs/rl/case-411-transfer-hit-guaranteed-block.md`) --

  L'ECRIVAIN de `+0x1D` est `IdunBattle.Operations.TransferHitOperation$$Execute`, qui remet a zero
  les 0x10 octets du `Nullable<IdunBattle.Core.AttackHit>` porte par le composant de l'unite CIBLE
  (`+0x98`). `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` a pose ce `PendingHit` juste
  avant d'emettre `EventTriggerType.PreAttackHit` (6) puis `PreAttackDamageHit` (7) ; il le RELIT
  apres, et sur `!HasValue` il met le degat a 0, arme le flag « never crit » du message (`+0x29`) et
  pose `DealDamageInfo[+0x1D] = 1`. `IdunBattle.Core.Services.DamagePrediction$$CalculateDamageOperation`
  route alors vers la surcharge `IdunBattle.Core.Services.DamageCalculations$$ApplyBlockDamage(
  blockChances, currentDamage)` (slot 4 d'`IDamageCalculations`, `currentDamage - blockChances[0]`
  puis `Math.Max(0, .)`) au lieu du couple `ApplyRandomEvasion` (slot 3) + `ApplyRandomBlockDamage`
  (slot 2) -- donc un block SANS AUCUN tirage, et `didBlock = 1` pose EN DUR.

  Les SEULS artefacts qui atteignent cet ecrivain sont les deux proprietaires DSL de
  `IdunBattleLogic.Entities.DSLBehaviors$$TransferHit` (xrefs entrantes, recoupees par
  `docs/rl/dsl-usage/dsl-usage-primitives.tsv` qui en compte EXACTEMENT 2) :
  `IdunBattleLogic.Entities.Abilities.Triggered.Loki.DrawFireAbility` et
  `...PrimarchOfTheFirstLegionAbility`.

L'invariant de port (dernier test) est la vraie garde : le jour ou l'un des deux entre dans le
registre du moteur, le coup transfere DOIT cesser de tirer son block -- sinon le port consomme des
tirages que le natif ne consomme pas, et tout le flux RNG de l'attaque diverge a partir de la. La
degradation serait SILENCIEUSE (aucune erreur, un simple desynchronisme de valeurs).

ASCII only.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_SYMBOLS = Path(__file__).resolve().parents[4] / "data" / "symbols"


def _enums() -> dict:
    build = (_SYMBOLS / "CURRENT").read_text(encoding="utf-8").strip() if (
        _SYMBOLS / "CURRENT").exists() else None
    cand = [_SYMBOLS / build] if build else []
    cand += [p for p in sorted(_SYMBOLS.iterdir()) if p.is_dir()]
    for d in cand:
        f = d / "frida" / "enums.tsv"
        if f.exists():
            out = {}
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.startswith("#") or "\t" not in line:
                    continue
                name, vals = line.split("\t", 1)
                out[name] = vals
            return out
    pytest.skip("table de symboles absente")


def _triggered_ability_ids() -> dict:
    vals = _enums().get("IdunBattle.Entities.Enum.TriggeredAbilityType")
    assert vals, "enum TriggeredAbilityType absente de enums.tsv"
    out = {}
    for kv in vals.split(","):
        if "=" not in kv:
            continue
        k, v = kv.split("=", 1)
        out[v] = int(k)
    return out


def test_les_deux_porteurs_dsl_de_transferhit_ont_leur_id_denum():
    """Les deux SEULS proprietaires de `DSLBehaviors$$TransferHit`, par leur `TriggeredAbilityType`.

    Ces ids sont ce qui relie le decompile au gameconfig et a `catalog_inject.graft_passive_ability`.
    Un renommage d'enum au prochain build casse ce test -- c'est exactement ce qu'on veut savoir."""
    ids = _triggered_ability_ids()
    assert ids.get("DrawFire") == 1109, ids.get("DrawFire")
    assert ids.get("PrimarchOfTheFirstLegion") == 1511, ids.get("PrimarchOfTheFirstLegion")


def test_les_porteurs_dunites_sont_ceux_mesures():
    """Les porteurs, derives du gameconfig (pas d'une liste ecrite a la main).

    MESURE (`unit_map find --ability`, build `rnca9r7q6c`) : `DrawFire` -> `blackNpc2Terminator`
    (npc) + `blackSmnTerminator` (SUMMON) ; `PrimarchOfTheFirstLegion` -> `darkaBossLion` (npc).
    Aucun HERO, aucune MoW, aucune relique : les trois etats de la gate relique ne s'appliquent pas,
    et la seule voie de confrontation est la GREFFE du passif (`case-92` §5bis volet passif) --
    ce que le test suivant verrouille."""
    import gameconfig as GC
    units = GC._index()
    carriers = {}
    for bucket in ("lineup", "npc", "summons"):
        for uid, u in (units.get(bucket) or {}).items():
            for ab in ((u or {}).get("passiveAbilities") or []) + (
                    (u or {}).get("activeAbilities") or []):
                carriers.setdefault(ab, set()).add(uid)
    assert carriers.get("DrawFire") == {"blackNpc2Terminator", "blackSmnTerminator"}, \
        sorted(carriers.get("DrawFire") or [])
    assert carriers.get("PrimarchOfTheFirstLegion") == {"darkaBossLion"}, \
        sorted(carriers.get("PrimarchOfTheFirstLegion") or [])


def test_le_summon_drawfire_na_pas_dinvocateur_dunite():
    """`blackSmnTerminator` est declare par `EnvFactionSummons:BlackLegion`, une ability
    d'ENVIRONNEMENT que PORTE aucune unite du catalogue.

    C'est le point qui interdit la voie « spawner l'invocateur » de la gate de confrontabilite
    (`case-92` §5bis recours 1 et 2) et impose le recours 3 (GREFFE). Le balayage est fait ici, pas
    suppose : on cherche l'ability qui declare ce summon, PUIS qui la porte."""
    import gameconfig as GC
    units = GC._index()
    decl = [name for name, ab in (units.get("abilities") or {}).items()
            if ((ab or {}).get("constants") or {}).get("unitId") == "blackSmnTerminator"]
    assert decl == ["EnvFactionSummons:BlackLegion"], decl
    holders = [uid for bucket in ("lineup", "npc", "summons")
               for uid, u in (units.get(bucket) or {}).items()
               if decl[0] in (((u or {}).get("passiveAbilities") or [])
                              + ((u or {}).get("activeAbilities") or []))]
    assert holders == [], holders


def test_le_montage_de_greffe_ecrit_bien_les_deux_entrees(tmp_path):
    """La voie de confrontation MESUREE par `probe_411_transfer_hit_guaranteed_block.py`.

    `catalog_inject.graft_passive_ability` doit poser LES DEUX ecritures -- `BC.Units[].
    PassiveAbilities = [1109]` (ce que monte `IdunBattle.Entities.Factories.UnitFactory$$
    AddConfiguredAbilities`) ET `BC.Abilities.PassiveAbilities['DrawFire']` (sans quoi la
    construction de l'arbre DSL du passif LEVE au deploiement). Le test verrouille le montage
    lui-meme : c'est lui qui a produit 6597/0 -> 3153/3488 en live."""
    import catalog_inject as CI
    out = tmp_path / "drawfire-grafted-bc.json"
    path, reports = CI.write_grafted_seed_bc(str(out), ["astraCreed:DrawFire"])
    assert reports[0]["abilityId"] == 1109, reports
    assert reports[0]["passiveAbilitiesAfter"] == [1109], reports
    bc = json.loads(Path(path).read_text(encoding="utf-8"))
    assert "DrawFire" in ((bc.get("Abilities") or {}).get("PassiveAbilities") or {})
    hit = [u for u in bc["Units"] if u["Id"] == "astraCreed"]
    assert hit and hit[0]["PassiveAbilities"] == [1109], hit[:1]


def test_porter_transferhit_exige_la_route_de_block_garanti():
    """L'INVARIANT DE PORT (la garde de cablage proprement dite).

    Tant que ni `DrawFire` (1109) ni `PrimarchOfTheFirstLegion` (1511) n'est porte, le champ
    `DealDamageInfo[+0x1D]` est INATTEIGNABLE dans le moteur : rien n'efface jamais de `PendingHit`.
    Le jour ou l'un des deux entre au registre, la boucle de coups DOIT exposer la route de garantie
    -- sinon le coup transfere continuerait a tirer son block (slots 2/3) alors que le natif prend le
    slot 4 SANS tirage, et le flux RNG de toute l'attaque diverge a partir de ce coup.

    Le contrat minimal choisi : l'intercepteur per-coup d'`ExecuteHit` (le foyer que #366-r1 a deja
    ouvert pour le `discard` d'`HarlequinsPanoply`) expose une accroche `should_transfer`."""
    from engine.runner.operations.triggers.dispatch.registry import (ABILITY_TRIGGERS,
                                                                     CUSTOM_TRIGGERED_ABILITIES)
    ported = set()
    for classes in list(ABILITY_TRIGGERS.values()) + list(CUSTOM_TRIGGERED_ABILITIES.values()):
        for cls in classes:
            tid = getattr(cls, "TRIGGERED_ABILITY_ID", None)
            if tid in (1109, 1511):
                ported.add(int(tid))
    if not ported:
        pytest.skip("ni 1109 ni 1511 porte -- +0x1D reste inatteignable (residu #411)")
    from engine.runner.operations.triggers.loki.harlequins_panoply import (
        HarlequinsPanoplyHitInterceptor)
    assert hasattr(HarlequinsPanoplyHitInterceptor, "should_transfer"), (
        "TransferHit porte (%s) SANS la route DealDamageInfo[+0x1D] : le coup transfere tirerait "
        "son block alors que le natif prend ApplyBlockDamage (slot 4) sans tirage." % sorted(ported))
