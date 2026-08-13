"""#1015 -- la garde du RECENSEUR DE TRAITS qui a remplace le seuil de frequence.

CE QU'ELLE GARDE, ET CONTRE QUOI. `audit_kit_coverage` ecartait du compte tout trait porte par plus
de `TRAIT_COMMON_MAX = 12` unites, en les declarant « presumes couverts ». Un seuil n'est pas un
critere : il repond a « ce trait est-il FREQUENT ? » quand la question est « le port sait-il
l'EVALUER ? ». La mesure a tranche -- 3 des 22 traits ainsi ecartes ne sont lus NULLE PART.

CINQ ETAGES, et chacun garde une propriete que le seuil n'avait pas :

  1. EXHAUSTIVITE -- aucun trait porte n'est ecarte. C'est la propriete que le seuil detruisait.
  2. NON-VIDE DE CHAQUE CANAL DECLARE -- un canal qui se viderait rendrait les etages suivants vrais
     par vacuite (la faute exacte des trois rouges que #1015 volet 1 a repares).
  3. LE CANAL `lecture` APPORTE REELLEMENT -- sans lui le compte retombe a l'ancien. Sans cet etage,
     on pourrait retirer le balayage AST sans qu'aucune assertion ne tombe.
  4. PAS DE LISTE BLANCHE -- un conteneur de module INCONNU du recenseur sort quand meme, sous son
     propre nom. C'est la parade au vice repete du depot (`unit_map find --ability` lisait 2 voies
     sur 5 et a fait classer DEAD un effet vivant).
  5. LE CLIQUET DES NON COUVERTS -- la liste des 5 est FIGEE. Qu'un trait en sorte (il est porte) ou
     qu'un NOUVEAU y entre (regression), le test le DIT.

ASCII only.
"""
from __future__ import annotations

import ast
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve()
PY = HERE.parents[1]
if str(PY) not in sys.path:
    sys.path.insert(0, str(PY))

import gameconfig as GC                                                   # noqa: E402
import trait_channels as TC                                               # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                   # noqa: E402

#: Ce qui doit faire REJOUER ce fichier. Le foyer (`trait_channels`) et son consommateur
#: (`audit_kit_coverage`) evidemment ; mais AUSSI les trois registres de trait et le mirror
#: `UnitTrait` -- une entree ajoutee a l'un d'eux change le canal d'un trait, et le cliquet des NON
#: COUVERTS doit alors etre reconsidere. `engine/**` entier serait le perimetre exact (le balayage
#: AST le lit en totalite) ; on declare les foyers qui le decident, pas les 622 fichiers qu'il lit.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/trait_channels.py",
    ),
    "build": False,
    "toujours": True,
    "raison": (
        "`toujours: True`, et c'est un RESULTAT mesure, pas un aveu. Ce fichier garde un recenseur "
        "dont le perimetre est TOUT `engine/**` : `trait_channels._balayage()` lit les 622 fichiers "
        "du paquet par `rglob`, et une simple LECTURE (`UnitTrait.Healer` ajoute dans n'importe "
        "quel module) suffit a faire basculer un trait de NON COUVERT a COUVERT. Or `rglob` ne "
        "laisse AUCUNE trace dans la fermeture d'imports : `--proposer` ne voit qu'un seul chemin "
        "(`trait_channels.py`), et une declaration reduite a lui serait le FAUX VERT que ce garde "
        "existe pour attraper -- le port pourrait porter `Healer` sans que le cliquet des cinq "
        "non couverts ne se rejoue. Les trois registres de trait "
        "(`effects/factory.TRAIT_DERIVED_ABILITIES`/`TRAIT_OWNER_EFFECTS`, "
        "`triggers/dispatch/registry.TRAIT_TRIGGERS`) et le mirror `entities/traits/unit_trait.py` "
        "sont dans le meme cas, et ne sont pas listes ici pour cette raison : ils sont deja "
        "couverts par `toujours`. S'y ajoute le gameconfig, qui decide la POPULATION des 61 traits "
        "portes et n'est atteint par aucun import (il est lu depuis `data/`)."
    ),
}

#: Les traits SANS AUCUN canal, mesures au 2026-08-13 sur le build `rnca9r7q6c`. Les cinq portent
#: une semantique de combat (gameconfig), donc AUCUN n'est « sans objet » -- residu #1015-r1.
NON_COUVERTS_MESURES = {
    "BeastSnagga", "CloseCombatWeakness", "Healer", "InstinctiveBehaviour", "TwoManTeam",
}


def _traits_portes() -> Counter:
    """Les traits REELLEMENT portes, TOUS SEAUX -- `lineup`, `npc` et `summons`.

    Les trois seaux, parce que `units.*` n'en porte pas d'autre (mesure : les 23 cles de `units.*`
    balayees, et `gameconfig._index()` code les memes trois). Un trait porte par les seuls `npc` est
    un trait que le moteur doit evaluer en bataille au meme titre qu'un autre."""
    out: Counter = Counter()
    idx = GC._index()
    for seau in ("lineup", "npc", "summons"):
        for _uid, u in (idx[seau] or {}).items():
            for t in (u.get("traits") or []):
                out[t] += 1
    return out


# ================================================================================================
# 1. EXHAUSTIVITE -- la propriete que le seuil detruisait
# ================================================================================================

def test_la_partition_ne_perd_aucun_trait_porte():
    portes = _traits_portes()
    assert portes, "aucun trait porte : le recenseur ne visite rien, son verdict ne prouve rien"
    part = TC.partition(sorted(portes))
    assert set(part) == set(portes), (
        "la partition n'est pas EXHAUSTIVE -- ecartes : %r" % sorted(set(portes) - set(part)))
    # Et chaque entree porte un verdict TRANCHE, jamais un « on ne sait pas ».
    for t, (couvert, canaux, _n) in part.items():
        assert isinstance(couvert, bool)
        assert couvert == bool(canaux), (
            "%s : verdict %r incoherent avec ses canaux %r" % (t, couvert, canaux))


def test_tout_trait_porte_existe_dans_le_mirror():
    """Un trait du gameconfig absent du mirror serait invisible du balayage (il ne peut etre ecrit
    ni en `UnitTrait.X` ni comme nom connu), donc compte NON COUVERT pour une mauvaise raison."""
    manquants = sorted(set(_traits_portes()) - {m.name for m in UnitTrait})
    assert manquants == [], (
        "traits portes absents du mirror `UnitTrait` : %r -- le recenseur ne peut pas les voir, et "
        "les rendrait non couverts par CECITE et non par mesure." % manquants)


# ================================================================================================
# 2-3. LES CANAUX : non vides, et `lecture` apporte reellement
# ================================================================================================

def test_chaque_canal_declare_est_non_vide_et_lecture_apporte_l_essentiel():
    """L'ecart 29 -> 56 est la MESURE de ce que le predicat d'avant ne voyait pas."""
    portes = sorted(_traits_portes())
    par_canal: Counter = Counter()
    for t in portes:
        for c in TC.canaux(t):
            par_canal[c] += 1
    for canal in ("trigger", "derived", "owner_eff", "effet_homonyme", "lecture"):
        assert par_canal[canal] > 0, (
            "le canal `%s` est VIDE : les etages qui s'appuient dessus deviennent vrais par "
            "vacuite. C'est la forme exacte des trois rouges repares par le volet 1 de #1015."
            % canal)
    sans_lecture = {t for t in portes if set(TC.canaux(t)) - {"lecture"}
                    or any(c.startswith("registre:") for c in TC.canaux(t))}
    avec = {t for t in portes if TC.canaux(t)}
    assert len(avec) > len(sans_lecture), (
        "le canal `lecture` n'apporte AUCUN trait que les registres ne portaient deja (%d vs %d) : "
        "le balayage AST pourrait etre retire sans qu'aucune assertion ne tombe."
        % (len(avec), len(sans_lecture)))


def test_le_module_de_DECLARATION_ne_compte_pas_comme_une_lecture():
    """`unit_trait.py` DECLARE le mirror : ce qu'on y lit n'est pas le moteur qui evalue un trait,
    c'est le mirror qui se definit. Compter ces mentions ferait rendre « couvert » sur la seule foi
    de l'existence du membre.

    ⚠ CE TEST A D'ABORD ETE ECRIT AVEUGLE, ET LA CONTRE-EPREUVE L'A MONTRE. Il assertionnait
    `sites(t) == []` sur les cinq traits NON COUVERTS -- or aucune des mentions du fichier de
    declaration ne les concerne, donc desarmer l'exclusion `_DECLARATION` le laissait VERT. Une
    garde qui ne peut pas rougir sur la faute qu'elle nomme est un faux vert. Il mesure desormais
    le fichier LUI-MEME, et assertionne son propre non-vide : s'il cessait d'y avoir des mentions a
    exclure, l'exclusion serait devenue inutile et le test le DIRAIT au lieu de passer."""
    decl = PY / TC._DECLARATION
    v = TC._Visiteur(TC._DECLARATION, TC._noms_de_traits())
    v.visit(ast.parse(decl.read_text(encoding="utf-8")))
    concernes = {t for t, _c, _l in v.trouves}
    assert concernes, (
        "le fichier de declaration ne porte AUCUNE mention de nom de trait : l'exclusion "
        "`_DECLARATION` ne retire plus rien. Ce n'est pas un vert -- verifier si le mirror a change "
        "de forme, et retirer l'exclusion devenue inerte plutot que de la garder par superstition.")
    balayage = TC._balayage()
    for t in sorted(concernes):
        depuis_decl = [s for s in balayage.get(t, ()) if s[1] == TC._DECLARATION]
        assert depuis_decl == [], (
            "%s est compte depuis le fichier de DECLARATION (%r) : le recenseur confond « le mirror "
            "nomme ce trait » avec « le moteur l'evalue »." % (t, depuis_decl[:2]))


# ================================================================================================
# 4. PAS DE LISTE BLANCHE -- un conteneur INCONNU sort sous son nom
# ================================================================================================

def test_un_conteneur_inconnu_du_recenseur_sort_sous_son_propre_nom(tmp_path):
    """LA PARADE AU VICE REPETE DU DEPOT, exercee pour de vrai.

    On ne verifie pas que le recenseur connait les bons registres -- on verifie qu'il n'a pas
    besoin de les connaitre. Un module qui declarerait demain `MON_REGISTRE_NEUF = {"Healer": ...}`
    doit faire sortir `Healer` sous `registre:MON_REGISTRE_NEUF`, sans qu'une ligne soit ajoutee a
    `trait_channels`. On l'exerce sur le VISITEUR, qui est le foyer de la derivation."""
    src = (
        "MON_REGISTRE_NEUF = {\n"
        "    'Healer': 1,\n"
        "    'TwoManTeam': 2,\n"
        "}\n"
        "def f(u):\n"
        "    return UnitTrait.BeastSnagga in u\n"
    )
    v = TC._Visiteur("faux/module.py", TC._noms_de_traits())
    v.visit(ast.parse(src))
    par_trait = {t: c for t, c, _l in v.trouves}
    assert par_trait.get("Healer") == "registre:MON_REGISTRE_NEUF", (
        "un conteneur INCONNU n'est pas nomme : %r. Le recenseur serait redevenu une liste "
        "blanche, et un registre neuf lui serait invisible." % par_trait)
    assert par_trait.get("TwoManTeam") == "registre:MON_REGISTRE_NEUF"
    # ... et hors conteneur, la mention reste une `lecture` : les deux roles se distinguent.
    assert par_trait.get("BeastSnagga") == "lecture", (
        "une mention hors conteneur doit sortir en `lecture`, rendu %r" % par_trait.get("BeastSnagga"))


# ================================================================================================
# 5. LE CLIQUET
# ================================================================================================

def test_les_traits_non_couverts_sont_exactement_ceux_mesures():
    """FIGE dans les DEUX sens (residu #1015-r1).

    Un trait qui SORT de la liste est une bonne nouvelle -- mais elle doit etre CONSTATEE, pas subie :
    le residu se ferme, et la ligne de backlog avec. Un trait qui ENTRE est une regression : le port
    a perdu la seule evaluation qu'il avait. Les deux se lisent dans le meme message."""
    portes = _traits_portes()
    muets = {t for t in portes if not TC.canaux(t)}
    assert muets, (
        "PLUS AUCUN trait non couvert : ce n'est pas un vert automatique. Soit le residu #1015-r1 "
        "est ferme (alors retire ce test et sa ligne de backlog), soit le recenseur a cesse de "
        "pouvoir rendre `[]` -- ce qui le rendrait incapable de mesurer quoi que ce soit.")
    entres = sorted(muets - NON_COUVERTS_MESURES)
    sortis = sorted(NON_COUVERTS_MESURES - muets)
    assert not entres, (
        "REGRESSION -- trait(s) devenu(s) non couvert(s) : %r. Le port a perdu la seule evaluation "
        "qu'il en avait ; porteurs : %s"
        % (entres, {t: portes[t] for t in entres}))
    assert not sortis, (
        "trait(s) desormais COUVERT(s) : %r -- bonne nouvelle a ENTERINER. Retire-les de "
        "`NON_COUVERTS_MESURES` et mets a jour la ligne #1015-r1 du backlog, dans le meme commit. "
        "Canaux : %s" % (sortis, {t: TC.canaux(t) for t in sortis}))
