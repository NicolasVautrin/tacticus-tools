"""#270-d LIVE -- `astarLysander` SE DEPLOIE, et `1231 TitanhammerSquad` devient confrontable.

CE QUE CES TESTS GARDENT. Le backlog declarait ce porteur bloque (« initAndStart: system error »)
et, avec lui, `1231 TitanhammerSquad` « confrontable par aucun montage ». La cause n'etait ni le
roster, ni l'injection, ni la seed, ni -- contrairement a la piste #254 -- une constante manquante
au passif `IconOfObstinacy` : c'est UN NOM DE TRAIT hors du vocabulaire de
`IdunBattle.Entities.Enum.UnitTrait`, dans un champ qui est TYPE
`List<IdunBattle.Entities.Enum.UnitTrait>`.

  `Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetUnitConfiguration` recopie
  `UnitProperties+0x18` dans `UnitConfiguration+0xd0` ;
  `IdunMetaLogic.UserProgress.Model.UnitPropertiesExtensions$$GetPlayerFacingTraits` lit ce MEME
  `UnitProperties+0x18` et rend `List<IdunBattle.Entities.Enum.UnitTrait>`.
  -> `initAndStart` step=deserialize BC -> `Newtonsoft.Json.Converters.StringEnumConverter$$ReadJson`
     -> `Newtonsoft.Json.Utilities.EnumUtils$$ParseEnum` -> `System.ArgumentException` LEVEE
     -> Frida rend « system error ».

Le montage (deux builds a UN SEUL BIT d'ecart) vit dans la fixture NOMMEE `lysander_deploy_case`
(`conftest.py` de la tranche) -> `scripts/python/probe_270d_lysander_deploy.py`. Le contraste est
la raison d'etre du fichier : le bras B seul dirait « ca marche » sans rien attribuer.

La garde OFFLINE du meme cas (le vocabulaire, sur les 669 unites du gameconfig) est
`tests/engine/test_270d_catalog_traits_enum.py` -- elle, ne demande aucune session.

ASCII only.
"""
from __future__ import annotations

ABILITY_ID = 1231           # IdunBattle.Entities.Enum.ActiveAbilityType.TitanhammerSquad
PORTEUR = "astarLysander"


def test_le_trait_hors_enum_est_bien_ce_qui_casse_le_build(lysander_deploy_case):
    """BRAS A -- re-inserer le seul nom hors enum suffit a faire echouer `initAndStart`.

    C'est la moitie qui ATTRIBUE : sans elle, le bras B ne distinguerait pas « le trait etait le
    coupable » de « quelque chose d'autre a ete repare entre-temps »."""
    r = lysander_deploy_case()
    assert r["dropped"], (
        "aucun trait ecarte : le build a rattrape le gameconfig, ce test n'a plus d'objet "
        "(mettre a jour #270-d plutot que de le laisser vert par vacuite)")
    assert r["a_ok"] is False, (
        "le bras A (traits %r) a MONTE alors qu'il porte un nom hors "
        "IdunBattle.Entities.Enum.UnitTrait -- l'attribution tombe : %r"
        % (r.get("traits_a"), r.get("a_verbatim")))
    assert "system error" in r["a_verbatim"] or "initAndStart" in r["a_verbatim"], (
        "le bras A echoue, mais pas par la faute attendue -- verbatim : %r" % r["a_verbatim"])


def test_le_porteur_se_deploie_et_expose_titanhammer_squad(lysander_deploy_case):
    """BRAS B -- le montage NOMINAL monte, et l'ability du cas est reellement portee.

    « Le build passe » ne suffit pas : ce qui rendait `1231` inconfrontable, c'est l'absence de
    porteur en bataille. On exige donc l'id AU decisionView, pas seulement un runner vivant."""
    r = lysander_deploy_case()
    assert r["b_ok"], "le montage nominal n'a pas monte : %r" % r.get("b_out")
    assert r.get("carries_ability"), (
        "%s se deploie mais n'expose pas %d TitanhammerSquad (abilities vues : %r)"
        % (PORTEUR, ABILITY_ID, r.get("abilities")))


def test_le_kit_de_combat_survit_au_filtre(lysander_deploy_case):
    """Le filtre ne doit retirer QUE la sous-faction inconnue -- pas un trait de combat.

    Sans cette garde, « ca se deploie » pourrait etre obtenu en vidant `Traits`, ce qui serait une
    degradation silencieuse (les gates de trait du natif deviendraient muettes sur ce porteur)."""
    r = lysander_deploy_case()
    for t in ("Imperial", "Hero", "TeleportStrike", "TerminatorArmour", "Resilient",
              "CrushingStrike"):
        assert t in r["traits"], "%s a perdu %s (traits: %r)" % (PORTEUR, t, r["traits"])
