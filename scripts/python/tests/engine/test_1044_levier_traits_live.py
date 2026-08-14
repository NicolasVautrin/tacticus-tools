"""#1044 -- GARDE : le jeu de traits d'une unite est FORCABLE au montage, `UnitTrait.Hero` compris.

CRITERE BINAIRE : une bataille peut-elle porter, dans le MEME camp, des unites dont l'ensemble
`HasTrait` EFFECTIF differe sur `UnitTrait.Hero` ? Sans ce regime, tout noeud
`UnitsWithTrait(., UnitTrait.Hero)` / `HasTrait(., 0x10)` est uniformement VRAI et donc
INVALIDABLE -- exactement le regime DEGENERE que la rarete a du quitter (#1039).

CE QUE CE FICHIER GARDE, et pourquoi chaque etage existe :
  1. le levier NU (`--unit-stat "<vis>:Traits=[...]"`) MORD -- retraits ET ajouts. La premisse
     inverse (#1042-r3 : « NE MORD PAS ») est FAUSSE, re-mesuree ici a chaque passe ;
  2. `Hero` RESISTE au levier nu, et il resiste SUR UNE UNITE QUI NE LE DEMANDE PAS -- c'est la
     signature de `IdunBattle.Operations.AddUnitOperation$$AddUnitTypeTraits`, pas d'un patch
     qui n'aurait pas ete applique ;
  3. le TRAIT PORTEUR (`NPC`) le fait tomber, et le regime devient SEPARANT ;
  4. le COUT est borne : les unites porteuses restent PLACEES, ACTIVABLES et CONTROLEES. Sans
     cet etage, on livrerait un levier qui casse le pilotage sans le dire (c'est le cas de
     `Summon`, l'autre trait porteur -- nomme dans le probe, pas utilise).

⚠ La comparaison se fait par MEMBRE D'ENUM : `combatSnapshot.units[].traits` publie des
ORDINAUX. Une comparaison de CHAINES a deja rendu un bras faussement VERT (#1042).

Montage : `probe_1044_levier_traits.py` (fixture `traits_forces_case`). ASCII only.
"""
from __future__ import annotations

import probe_1044_levier_traits as LT
from engine.entities.traits.unit_trait import UnitTrait

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # LE MONTAGE lui-meme : cas nommes, trait porteur, lecture du canal.
        "scripts/python/probe_1044_levier_traits.py",
        # La porte pytest du montage.
        "scripts/python/tests/engine/conftest.py",
        # Le MIRROR de l'enum : l'etage 0 confronte ses 105 membres au build, et les trois
        # que `AddUnitTypeTraits` force portent leur nom ici.
        "scripts/python/engine/entities/traits/unit_trait.py",
        # Le levier `--unit-stat` et le `--place` dont l'etage COUT verifie qu'il tient.
        "scripts/python/rl_duel.py",
    ),
    # L'etage 0 LIT `data/symbols/<build>/frida/enums.tsv` : un changement de build renumerote
    # l'enum, donc change le verdict sans qu'aucun chemin Python ne bouge.
    "build": True,
    "toujours": False,
    "raison": ("perimetre DERIVE de la mesure : le montage (probe #1044), sa porte pytest, le "
               "mirror UnitTrait et rl_duel -- tous dans la fermeture d'imports, declares quand "
               "meme parce qu'ils sont le SUJET. `build: True` parce que l'etage 0 confronte "
               "l'enum a `data/symbols/<build>/frida/enums.tsv`. Le canal mesure vit hors "
               "Python (`frida/hooks/features/ai-step/rpc-snapshot.ts`, ajoute explicitement "
               "ci-dessous) : aucun import ne le tire, et un changement la-bas change ce que ce "
               "fichier lit."),
}
DECLENCHEUR["chemins"] += ("frida/hooks/features/ai-step/rpc-snapshot.ts",)

HERO = UnitTrait.Hero.name          # jamais l'ordinal nu : cf. l'avertissement d'en-tete
PORTEURS = ("adeptCanoness", "adeptRetributor")
CONTROLE = "astraBullgryn"


# ------------------------------------------------------------------ etage 0 : offline


def test_le_mirror_unit_trait_est_apparie_au_build():
    """Sans cet etage, les ordinaux du canal seraient ininterpretables et tout le reste du
    fichier mesurerait la mauvaise chose. Il verifie AUSSI que les trois membres que
    `AddUnitTypeTraits` force (`Hero` 0x10, `NPC` 0x7e6, `Summon` 0x2) portent ces noms-la."""
    assert LT.etage0_appariement(verbeux=False) == 0


def test_sans_hero_ajoute_le_trait_porteur():
    """`sans_hero` est le geste que `--unit-stat` seul ne sait pas faire. Il RETIRE `Hero` de la
    demande (l'ecrire ne servirait a rien : la config n'est pas ce qui le pose) et AJOUTE le
    porteur."""
    assert LT.sans_hero(["Psyker"]) == ["Psyker", "NPC"]
    assert LT.sans_hero(["Hero", "Psyker"]) == ["Psyker", "NPC"]
    assert LT.sans_hero(["NPC"]) == ["NPC"]            # idempotent, pas de doublon


# ------------------------------------------------------------------ etage 1 : le levier NU


def test_le_levier_nu_mord_en_retrait_et_en_ajout(traits_forces_case):
    """#1042-r3 disait `--unit-stat "<vis>:Traits=[...]" NE MORD PAS`. Re-mesure : il mord."""
    m = traits_forces_case("levier-nu")
    for vis in PORTEURS:
        avait = set(m["seed_traits"][vis] or [])
        veut = set(m["demande"][vis])
        porte = m["mesure"][vis]
        assert (avait - veut) - porte, (
            f"{vis} : AUCUN retrait n'a mordu (seed={sorted(avait)} demande={sorted(veut)} "
            f"mesure={sorted(porte)})")
    # L'AJOUT aussi, sur un trait que l'unite n'avait pas : un levier qui ne saurait que
    # retirer laisserait la moitie des montages hors de portee.
    ajoute = set(m["demande"]["adeptRetributor"]) - set(m["seed_traits"]["adeptRetributor"] or [])
    assert ajoute and ajoute <= m["mesure"]["adeptRetributor"], (
        f"ajout non mordu : {sorted(ajoute)} absent de {sorted(m['mesure']['adeptRetributor'])}")


def test_hero_resiste_au_levier_nu(traits_forces_case):
    """`Hero` est porte alors que la demande ne le contient PAS -> il vient d'une AUTRE source
    que `BC.Units[].Traits`. C'est ce que dit `AddUnitTypeTraits`, et c'est ce qui interdit de
    lire l'etage precedent comme « le patch n'a pas ete applique »."""
    m = traits_forces_case("levier-nu")
    for vis in PORTEURS:
        assert HERO not in m["demande"][vis]
        assert HERO in m["mesure"][vis], (
            f"{vis} : `Hero` absent de la mesure -- le forcage d'AddUnitTypeTraits aurait "
            f"disparu, la prose du probe et la fixture seraient a relire "
            f"(mesure={sorted(m['mesure'][vis])})")


# ------------------------------------------------------------------ etage 2 : le mur tombe


def test_le_trait_porteur_retire_hero_et_le_regime_devient_separant(traits_forces_case):
    """LE LIVRABLE : dans le MEME camp, deux unites SANS `Hero` et trois AVEC."""
    m = traits_forces_case("hero-separant")
    for vis in PORTEURS:
        assert HERO not in m["mesure"][vis], (
            f"{vis} porte toujours `Hero` malgre le trait porteur "
            f"(demande={m['demande'][vis]} mesure={sorted(m['mesure'][vis])})")
        assert UnitTrait.NPC.name in m["mesure"][vis]
    avec = {v for v, t in m["mesure"].items() if HERO in t}
    sans = {v for v, t in m["mesure"].items() if HERO not in t}
    assert avec and sans, (
        f"regime DEGENERE : avec Hero={sorted(avec)} sans Hero={sorted(sans)} -- un gate "
        f"`UnitsWithTrait(., Hero)` y serait uniformement vrai, donc invalidable")
    assert m["separants"], "aucune paire d'unites du meme camp aux traits differents"


def test_le_controle_recoit_hero_sans_l_avoir_demande(traits_forces_case):
    """CONTRE-EPREUVE dans le MEME build : l'unite qu'on mute SANS trait porteur recoit `Hero`.
    Sans elle, l'absence de `Hero` chez les porteurs pourrait venir du montage entier (un
    `--unit-stat` ignore, un seed different), pas du trait porteur."""
    m = traits_forces_case("hero-separant")
    assert HERO not in m["demande"][CONTROLE]
    assert HERO in m["mesure"][CONTROLE], (
        f"{CONTROLE} : le forcage n'a pas eu lieu, la contre-epreuve ne discrimine plus "
        f"(mesure={sorted(m['mesure'][CONTROLE])})")
    # et le reste de SA demande a bien mordu -> ce n'est pas « rien n'a ete applique »
    assert set(m["demande"][CONTROLE]) <= m["mesure"][CONTROLE]


# ------------------------------------------------------------------ etage 3 : le COUT


def test_le_cout_du_levier_est_borne(traits_forces_case):
    """Les unites porteuses restent PLACEES, ACTIVABLES et CONTROLEES. C'est ce qui separe le
    porteur `NPC` du porteur `Summon` : mesure du 2026-08-14, une p-unit `Summon` n'entre pas
    dans `decisionView.toActivate` (#291) et son `--place` n'est meme pas tenu."""
    m = traits_forces_case("hero-separant")
    for vis in m["mesure"]:
        assert tuple(m["positions"][vis]) == tuple(m["demandees"][vis]), (
            f"{vis} : pose en {m['positions'][vis]} au lieu de {m['demandees'][vis]}")
        assert m["activables"][vis] is True, f"{vis} n'est pas dans decisionView.toActivate"
        assert m["ctrl"][vis] is True, f"{vis} n'est pas controlee par le joueur courant"
