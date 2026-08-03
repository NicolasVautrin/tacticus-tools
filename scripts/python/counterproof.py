"""#462-r6 -- LE ROUGE DE SCENARIO A UN NOM, et il le porte JUSQU'AU RAPPORT.

LE PROBLEME QUE CE MODULE FERME
-------------------------------
Le balayage #462 a ventile les rouges live en PORT / MONTAGE / HARNAIS, et a constate que la
ventilation ne suffit pas : **3 des 8 rouges n'accusaient NI le port NI le harnais**. Ils
accusaient le SCENARIO -- la mutation que le test fabrique pour prouver qu'il discrimine avait
cesse de casser, ou l'echantillon ne realisait plus le regime vise.

Or un rouge de scenario ressemble TRAIT POUR TRAIT a un rouge de port dans le message du test :

    AssertionError: scarabhive : le modele d'avant rend 10 genrand pour 10 live [...]

Un lecteur (ou le ledger de `probe_462`, qui conserve le symptome VERBATIM) ira debugger le
moteur pour rien. C'est du temps deja perdu deux fois -- et c'est exactement la forme de #533,
ou le rouge accusait le MONTAGE pendant que le `pytest.fail` disait vrai sur le FAIT.

CE QU'EST UN CONTRE-CONTROLE, ET OU PASSE LA FRONTIERE
------------------------------------------------------
Un CONTRE-CONTROLE est une assertion dont le sujet n'est PAS le port, mais une **mutation
FABRIQUEE PAR LE TEST LUI-MEME** : un modele alternatif rejoue (`legacy=True`), un masque prive
d'un bit, un helper court-circuite. Elle exige que la mutation CASSE. Si elle ne casse plus, ce
qui est mort est la GARDE, pas le moteur.

    sujet = le port REEL, sur l'etat live          -> assertion de FOND    -> rouge de PORT
    sujet = une mutation fabriquee par le test     -> contre-controle      -> rouge de SCENARIO
    sujet = le regime que le montage doit realiser -> echantillon          -> rouge de SCENARIO

C'est l'ASSERTION qui porte la distinction, jamais le test : `test_valkyrie_strike_targeting_
mask_matches_native` melange les trois dans UNE fonction (accord natif/port = fond, gains =
contre-controle, contrefactuel = contre-controle). Un marqueur pytest au niveau du test serait
donc FAUX par construction.

POURQUOI UN TYPE D'EXCEPTION DEDIE, ET PAS UN PREFIXE DE MESSAGE
----------------------------------------------------------------
Un prefixe convenu (`"CONTRE-CONTROLE INERTE: ..."` ecrit a la main dans une f-string) aurait
suffi a un LECTEUR humain attentif. Il a trois defauts, tous mesurables :

  * il n'est pas MECANIQUE -- rien ne le distingue d'un rouge de port dont la prose contient les
    memes mots, donc aucun outil ne peut classer sans lire ;
  * il n'a pas de point d'ancrage -- chacun l'ecrit a sa facon, et il derive ;
  * il ne force RIEN. Nommer la cause sans nommer le REMEDE laisse le lecteur au meme point.

Le type d'exception, lui, traverse toute la chaine SANS QU'UNE LIGNE D'OUTILLAGE CHANGE :

    pytest short summary : FAILED tests/...::test_x - InertCounterproof: CONTRE-CONTROLE INERTE ...
    junitxml <failure message=...> : "InertCounterproof: CONTRE-CONTROLE INERTE -- ..."
    ledger `probe_462`  : le symptome verbatim, donc le NOM DU TYPE, dans
                          `scripts/ratchets-462-live-attestations.json`

C'est le point decisif : `probe_462` conserve `child.get("message")` du JUnit, qui commence par
le nom de la classe d'exception. Le verdict devient donc lisible depuis le LEDGER, pas seulement
depuis un terminal ouvert au bon moment -- et c'est le canal par lequel le prochain balayage du
parc live rendra sa ventilation.

Les helpers exigent enfin les QUATRE champs qui manquaient a chacun des trois rouges : la
mutation, ce qu'elle devait casser, ce qu'on a mesure, et le REMEDE. Sans le dernier, le nom
seul renvoie le lecteur au meme carrefour.

CE QUE CE MODULE NE PRETEND PAS FAIRE
-------------------------------------
Il ne DECIDE pas qu'une assertion est un contre-controle -- personne ne peut le deriver du code
(`m0_n > live_n` et `m1_n == live_n` sont syntaxiquement jumeaux et de natures opposees). C'est
une declaration d'AUTEUR, comme l'est le choix d'ecrire un contre-controle. Ce qui EST garde
mecaniquement, c'est que la declaration ne mente pas : le marqueur ne peut pas etre usurpe par
une prose d'assertion ecrite a la main, et le canal (type -> JUnit -> ledger) ne peut pas se
degrader en silence. Le garde est `tests/test_462r6_counterproof_marker_offline.py`, joue par
`probe_457` (perimetre DERIVE de `git ls-files scripts/python/tests`), donc par la banque.

ASCII only (cp1252) : ces messages partent vers la console et vers le XML JUnit.
"""
from __future__ import annotations

MARKER_COUNTERPROOF = "CONTRE-CONTROLE INERTE"
MARKER_SAMPLE = "ECHANTILLON NON CONFRONTABLE"

# Les deux marqueurs, pour un balayage (le garde offline les derive d'ici, il ne les recopie pas).
MARKERS = (MARKER_COUNTERPROOF, MARKER_SAMPLE)


class ScenarioRed(AssertionError):
    """ROUGE DE SCENARIO : l'echec n'accuse NI le port NI le harnais.

    Sous-classe d'`AssertionError` a dessein -- pytest la traite exactement comme un echec
    d'assertion (meme couleur, meme comptage, meme `<failure>` JUnit), et un `except
    AssertionError` existant continue de la voir. Ce qui change est le NOM, et c'est tout ce
    qu'on veut : le rouge reste un rouge, il dit seulement qui il accuse."""


class InertCounterproof(ScenarioRed):
    """La mutation que le test FABRIQUE pour prouver qu'il discrimine ne casse plus rien.

    Deux causes possibles, et elles se tranchent AVANT toute edition :
      * le PORT S'EST AMELIORE -- le regime vise n'existe plus, ou une autre porte (portee
        depuis) rend le meme refus : re-crafter la mutation pour qu'elle re-discrimine ;
      * le PORT A REGRESSE -- alors ce n'est PAS un rouge de scenario, et il se reclasse en
        rouge de PORT. Le discriminant est l'assertion de FOND du meme fichier : si elle passe,
        le port accorde toujours avec le natif."""


class UnconfrontableSample(ScenarioRed):
    """Le montage ne realise plus le REGIME que la mesure exige.

    L'echantillon a derive (unite devenue non spawnable, pool tombe a 1, geometrie qui ne
    separe plus deux modeles). Rien n'a ete confronte : ce n'est ni un verdict sur le port, ni
    un verdict sur le harnais -- c'est une mesure INVALIDE."""


def _bloc(titre: str, marker: str, mutation: str, doit_casser: str, observe: str,
          remede: str) -> str:
    return ("%s -- %s\n"
            "  mutation    : %s\n"
            "  doit casser : %s\n"
            "  observe     : %s\n"
            "  remede      : %s" % (marker, titre, mutation, doit_casser, observe, remede))


def assert_counterproof(bites: bool, *, mutation: str, doit_casser: str, observe: str,
                        remede: str) -> None:
    """Assertion d'un CONTRE-CONTROLE : `bites` doit etre vrai, sinon la garde est creuse.

    Les quatre champs sont OBLIGATOIRES et positionnels-interdits (kwargs seulement) : ce sont
    eux qui separent << mon controle ne mord plus >> de << le moteur a diverge >>.

      mutation    ce que le test FABRIQUE (le modele M0, le masque prive d'un bit, ...)
      doit_casser ce que cette mutation doit rendre FAUX si le scenario discrimine
      observe     la mesure, chiffree
      remede      le geste : re-crafter quoi, ou reclasser en rouge de PORT et pourquoi
    """
    if bites:
        return
    raise InertCounterproof(_bloc("ce rouge n'accuse NI le port NI le harnais",
                                  MARKER_COUNTERPROOF, mutation, doit_casser, observe, remede))


def assert_sample_confrontable(realise: bool, *, mutation: str, doit_casser: str, observe: str,
                               remede: str) -> None:
    """Assertion d'ECHANTILLON : le montage realise-t-il le regime que la mesure exige ?

    Meme quatre champs (`mutation` = le regime monte, `doit_casser` = ce qu'il doit realiser) :
    un seul vocabulaire pour les deux faces du rouge de scenario."""
    if realise:
        return
    raise UnconfrontableSample(_bloc("rien n'a ete confronte -- la mesure est INVALIDE",
                                     MARKER_SAMPLE, mutation, doit_casser, observe, remede))
