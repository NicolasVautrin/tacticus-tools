"""GARDE #952-r1 (OFFLINE PURE) -- la geometrie de `1190 HuntersBeyondDeath` reste HORS du registre,
et le GATE du malus n'est PAS ce selecteur.

`#952-r1` est **fermé EN REFUS**, et ce fichier est ce qui rend le refus verifiable plutot que
declaratif. Le `CreateTargetSelector` de `HuntersBeyondDeathEffect` est LU et mirrore verbatim dans
la docstring de sa classe :

    UnitsWithTrait( SurroundingEnemies(Owner@+0x30, <+0x50>, range = 2, unique = 1, selType = 3),
                    0x3ea = Psyker, 3 )

Il MATERIALISE `EffectComponent.Targets@+0x48` -- ce que l'UI affiche et ce que lirait
`IdunBattleLogic.Entities.DSLTriggers$$IsEffectTarget`. Mais **aucun lecteur porte d'`IsEffectTarget`
ne le consomme pour 1190** : re-mesure du jour, `EFFECT_TARGET_SELECTORS` porte `1026` et `1191`, et
les consommateurs du foyer (`playbook/psyker.py`, `playbook/savior_protocols.py`,
`entities/effects/loki/damage_reduction.py`, `runner/operations/movement.py`) n'interrogent que ces
deux-la. L'inscrire aujourd'hui serait un port SPECULATIF -- ce que l'en-tete du foyer refuse
explicitement.

⚠ LA CONFUSION CONTRE LAQUELLE CE FICHIER GARDE. Le GATE du malus n'est PAS ce selecteur : il
RE-DERIVE la geometrie (`NOT AmountIsGreater(MinDistance(EffectSource, Caster@+0x48), Direct(2))`)
et porte sur l'**ATTAQUANT** du coup courant, la ou le selecteur vise **les Psykers ennemis**. Deux
sujets differents. Router le gate par `IsEffectTarget` changerait donc de sujet, en silence -- et
c'est exactement ce qu'un lecteur pourrait faire en voyant une geometrie « lue mais pas branchee ».

ASCII only.
"""
from __future__ import annotations

from engine.entities.effect_targets import EFFECT_TARGET_SELECTORS, is_effect_target
from engine.entities.effect_type import EffectType
from engine.entities.effects.loki.hunters_beyond_death import HuntersBeyondDeathEffect

DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/effect_targets.py",
        "scripts/python/engine/entities/effects/loki/hunters_beyond_death.py",
        "scripts/python/engine/entities/effect_type.py",
    ),
    "build": True,          # le gate lit le gameconfig d'`AppData` (la magnitude `dmgReduction`)
    "toujours": False,
    "raison": "Il garde un REFUS : la geometrie de 1190 est lue mais NON consommee, et le gate du "
              "malus porte sur un AUTRE sujet. Inscrire l'une en croyant brancher l'autre ne leve "
              "rien et deplace le malus des attaquants vers les cibles.",
}

HBD = int(EffectType.HuntersBeyondDeath)                              # 0x4a6 = 1190
PSYKER_SUPPRESSION = int(EffectType.HuntersBeyondDeathPsykerSuppression)   # 0x4a7 = 1191
BIG_TARGET_ADJACENT = int(EffectType.BigTarget_AdjacentEffect)        # 0x402 = 1026
NIVEAU, MULT = 50, 100


class _MondeVide:
    """Substrat minimal : `is_effect_target` doit sortir AVANT de le toucher (pas d'entree)."""

    def unit_ids(self):
        raise AssertionError("le registre a ete consulte APRES avoir accepte 1190")

    def carries(self, uid, effect_type):
        raise AssertionError("le registre a ete consulte APRES avoir accepte 1190")


def _effet() -> HuntersBeyondDeathEffect:
    return HuntersBeyondDeathEffect(name=EffectType.HuntersBeyondDeath.name, effect_type=HBD,
                                    target=1, active=True,
                                    ability_level=NIVEAU, ability_variables_multiplier=MULT)


def _ctx(att_pos, owner_pos=(0, 0)) -> dict:
    """Le contexte que l'agregateur d'aura defense thread : un Psyker ENNEMI a `att_pos`."""
    return {"owner_team": 1, "owner_pos": owner_pos, "tgt_team": 1,
            "att_team": 2, "att_pos": att_pos, "att_traits": ["Psyker"]}


# ------------------------------------------------------------------ le registre, et son contenu

def test_le_registre_ne_porte_QUE_les_geometries_CONSOMMEES():
    """Cliquet du registre. `1190` n'y est pas, et les DEUX qui y sont ont chacune un lecteur porte
    (`1026` par `damage_reduction`/`movement`, `1191` par `playbook/psyker`). Un ajout doit donc
    etre conscient -- et s'accompagner de son lecteur."""
    assert set(EFFECT_TARGET_SELECTORS) == {BIG_TARGET_ADJACENT, PSYKER_SUPPRESSION}
    assert HBD not in EFFECT_TARGET_SELECTORS
    assert HBD != PSYKER_SUPPRESSION and HBD == 1190 and PSYKER_SUPPRESSION == 1191


def test_une_geometrie_NON_PORTEE_rend_None_jamais_False():
    """La degradation est NOMMEE : `None` = « non porte ». Rendre `False` affirmerait que le refresh
    natif a laisse la liste VIDE -- ce qu'on n'a pas mesure. Le monde n'est meme pas touche."""
    assert is_effect_target(_MondeVide(), 42, HBD) is None


# ------------------------------------------------------- le GATE : un AUTRE sujet, un AUTRE chemin

def test_le_gate_du_malus_MORD_dans_les_deux_sens():
    """CONTROLE DE NON-DEGENERESCENCE, sans lequel l'etage suivant serait vide de sens :
    `NOT AmountIsGreater(MinDistance(src, Caster), Direct(2))` est bien `d <= 2`."""
    eff = _effet()
    assert eff.create_aura_defense_damage_malus_for_ally(_ctx((2, 0))) is not None   # d = 2
    assert eff.create_aura_defense_damage_malus_for_ally(_ctx((3, 0))) is None       # d = 3
    # ... et le TRAIT est un conjoint distinct de la distance.
    sans_psyker = dict(_ctx((2, 0)), att_traits=[])
    assert eff.create_aura_defense_damage_malus_for_ally(sans_psyker) is None


def test_INSCRIRE_1190_au_registre_ne_change_RIEN_au_gate(monkeypatch):
    """LE CRAN QUI COMPTE. Le selecteur materialise `Targets` (les Psykers ENNEMIS) ; le gate
    re-derive `MinDistance` et porte sur l'ATTAQUANT. Les deux ne partagent aucun chemin -- donc
    brancher l'un ne branche pas l'autre, et un lecteur qui croirait << activer >> le malus en
    inscrivant la geometrie n'aurait rien active du tout.

    On INSCRIT reellement 1190 (avec une geometrie qui rendrait TOUT LE MONDE cible) et on verifie
    que les quatre verdicts du gate sont inchanges."""
    monkeypatch.setitem(EFFECT_TARGET_SELECTORS, HBD, lambda world, uid: {1, 2, 3, 42})
    assert HBD in EFFECT_TARGET_SELECTORS                    # la mutation A mordu
    eff = _effet()
    assert eff.create_aura_defense_damage_malus_for_ally(_ctx((2, 0))) is not None
    assert eff.create_aura_defense_damage_malus_for_ally(_ctx((3, 0))) is None
    sans_psyker = dict(_ctx((2, 0)), att_traits=[])
    assert eff.create_aura_defense_damage_malus_for_ally(sans_psyker) is None
    ami = dict(_ctx((2, 0)), att_team=1)                     # `NOT AreFriends(src, Caster)`
    assert eff.create_aura_defense_damage_malus_for_ally(ami) is None
