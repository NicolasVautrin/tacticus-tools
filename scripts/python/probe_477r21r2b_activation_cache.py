#!/usr/bin/env python3
"""#477-r21-r2 volet B -- le CACHE qui choisit ce qui s'active, confronte sur sa SEQUENCE.

    python probe_477r21r2b_activation_cache.py [--session N] [--boards MC1_67,C1_02] [--tours 1]

CE QU'IL MESURE, ET POURQUOI PAS COMME LES QUATRE CRANS PRECEDENTS
------------------------------------------------------------------
`AbilityAndEffectCache` n'emet AUCUNE ligne : il rend un ENSEMBLE ORDONNE, que
`IdunBattle.Operations.EvaluateTriggerOperation$$ExecuteInternal` parcourt. On ne peut donc pas
le confronter en comparant deux textes de flux (#477-r18..r22). L'oracle est ailleurs, et il
EXISTE DEJA : le hook `triggerTrace` (`frida/hooks/features/trigger-trace.ts`) intercepte
`IdunBattle.Entities.Abilities.BaseTriggeredAbility$$ShouldTrigger`, appele UNE FOIS PAR ENTREE
retenue du parcours, DANS L'ORDRE. Sa trace est donc la sequence `active[trigger]` observee.

  ⚠ AUCUN CAPTEUR NEUF N'EST POSE. Le hook est arme par defaut, en lecture seule, et ce probe ne
    le remet JAMAIS a zero -- `triggerTraceReset` effacerait le ring des autres agents.

CE QUI REND CE PROBE REPRODUCTIBLE (#477-r28) -- IL NE L'ETAIT PAS
------------------------------------------------------------------
Mesure : deux passages sur le MEME commit rendaient des verdicts OPPOSES (19 evenements,
24 ruptures / 90 couples, 10 passes courtes hors sous-sequence, ROUGE ; puis 10, 1 / 9, 0, VERT).
La cause n'etait PAS le seed -- il valait deja 777 -- mais la LECTURE UNIQUE sur un ring PARTAGE
de 200 entrees : le `build` du scenario 5v5 produit 1333 fires, dont 1133 evinces avant lecture
(85 %), et LESQUELS survivaient dependait du bruit des voisins. Un corpus ampute au hasard coupe
les passes, ce qui FABRIQUE des (I4) hors sous-sequence et des (I2) qui n'existent pas.

Trois crans, dans l'ordre ou ils mordent :

  1. SEED EXPLICITE (`--seed`, defaut `R19.SEED`) -- imprime, plus suppose ;
  2. COLLECTE SANS PERTE (`Collecteur`) -- poll continu pendant chaque etape. Les `seq` du hook
     etant strictement croissants, ce qui manque s'ENUMERE : `Fenetre.trous` est l'intervalle
     `]depuis, total]` prive de ce qu'on a lu. L'ancien `perdus = attendus - len(fires)`
     additionnait deux grandeurs de sens oppose (perte et contamination) et pouvait rendre 0 sur
     un corpus a la fois ampute et pollue ;
  3. VERDICT TRI-ETAT -- une fenetre a trous est ECARTEE du corpus ; une contamination AVEREE
     (`sonde_silence`) rend le scenario NON MESURE. Ni vert, ni rouge, et `rc=2` si aucun
     scenario n'est exploitable. Meme discipline que le tri-etat d'`host_inputs.py` ;
  4. CERTIFICATION PAR CONCORDANCE (`--repetitions`, defaut 2) -- et c'est le cran qui MORD, les
     trois autres ne suffisant pas. Mesure : un scenario a rendu `0 fire etranger` a ses trois
     sondes ET 23 evenements / 15 ruptures / 5 passes hors sous-sequence, soit trois fois le
     corpus propre. La sonde n'echantillonne que quelques secondes sur une trentaine ; elle rate
     donc les voisins a rafales. Le seul critere EXACT est que deux passages a seed identique
     rendent la MEME empreinte -- sinon le corpus a ete pollue, et rien ne dit lequel des deux.

  ⚠ CE QUI RESTE IRREDUCTIBLE SANS CAPTEUR NEUF : le hook n'emet AUCUN identifiant de runner, et
    les identifiants d'entite sont attribues PAR MATCH (mesure : deux runners du meme board
    portent tous deux `49`/`51`). Aucun champ d'un fire ne dit donc de quelle bataille il vient.
    La sonde de silence DETECTE la contamination (delta non nul = preuve) mais ne peut pas
    prouver son absence -- le probe rend « aucune activite etrangere DETECTEE par N sonde(s) »,
    jamais « corpus propre ».

TROIS INVARIANTS DERIVES, refutables par un seul contre-exemple :

  (I1) STABILITE -- pour un meme `EventTriggerType`, deux publications successives parcourent la
       MEME sequence. C'est ce que « cache » veut dire : le natif ne recalcule pas par evenement,
       il lit `active[trigger]`, peuple par `AddEntity`/`AddAbility`/`AddEffect`. Un port qui
       reconstruirait son registre a chaque evenement (ce que fait `dispatch/core.py` aujourd'hui)
       n'a AUCUNE raison structurelle de rendre deux fois la meme sequence.

  (I2) MONOTONIE INTER-ENTITE -- au sein d'une passe, les identifiants d'entite porteuse sont NON
       DECROISSANTS. Derive de deux lectures conjointes :
         * `AddSorted` (`AbilityAndEffectCache$$AddSortedu003Cobjectu003E`) insere devant le
           premier element de priorite STRICTEMENT inferieure, donc APRES tous les egaux -- a
           priorites egales il degenere exactement en `append` ;
         * `AddEntity` est appele dans l'ordre de CREATION des entites, et l'identifiant ECS est
           attribue par `MatchComponent$$NextId`, monotone croissant (#477-r21-r3).
       Cet invariant ne copie RIEN du flux : c'est une implication a sens unique sur la seule
       sequence observee. ⚠ IL EST REFUTABLE, ET SA REFUTATION EST UNE DECOUVERTE, PAS UN ECHEC :
       un porteur dont `get_Priority` ne rend pas `AbilityPriority.Normal` remonterait devant ses
       aines, et ce probe l'ISOLERAIT nominativement -- c'est le seul canal qui puisse rendre ces
       valeurs, dedupliquees dans le binaire (meme faux negatif que #170).

  (I3) RE-DERIVATION -- le port RE-PRODUIT la sequence. On donne a
       `engine.runner.caches.AbilityAndEffectCache` les COUPLES observes (entite, ability) sans
       leur ORDRE inter-entite, dans un ordre volontairement PERTURBE, et on lui demande la
       liste : elle doit egaler la sequence native. C'est `add_sorted` + le pre-peuplement du
       dictionnaire qui sont mesures ici.

BORNE (c) -- CE QUI RESTE COPIE, ET IL FAUT LE LIRE AVANT LE VERT :
  * la SELECTION -- quelles abilities/effets ecoutent quel `EventTriggerType`. Elle vit dans
    `ability.<slot 3>` et `effect.<slot 0x12>`/`<slot 0x2d>`, corps dedupliques et blobs
    `global-metadata.dat` : non lisibles de Ghidra (meme cause que #477-r26) ;
  * l'ordre INTRA-ENTITE des abilities d'un meme porteur. Il vient de
    `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` (passives -> relique ->
    actives) puis de `TriggeredAbilityComponent$$TryAdd` ; il n'est PAS porte. (I2) ne porte donc
    que sur l'axe INTER-entite, et le probe le dit au lieu de compter les deux ensemble ;
  * les valeurs de `Priority` par porteur -- entree du port, cf. l'entete du module de cache.

DISCIPLINE : un runner a la fois, dispose dans le `finally`, state-files sous `logs/`.
ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import probe_477r15a_stream_conformance as R15A  # noqa: E402
import probe_477r19_process_removals as R19  # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType  # noqa: E402
from engine.runner.caches.ability_and_effect_cache import AbilityAndEffectCache  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / "logs"

MesureImpossible = R15A.MesureImpossible

#: Le ring de `trigger-trace.ts` (`FIRE_LOG_MAX`). Il est PARTAGE entre tous les agents et ne
#: garde que 200 entrees : une LECTURE UNIQUE apres une etape qui en produit davantage ne rend pas
#: « un corpus tronque », elle rend UNE QUEUE ARBITRAIRE. Mesure du 2026-08-06, avant correctif :
#: le `build` du scenario 5v5 produit 1333 fires, dont 1133 evinces avant lecture -- 85 % du
#: corpus n'etait jamais vu, et QUELS 200 survivaient dependait du bruit des voisins.
#:
#: ⚠ C'EST UN REPLI, PAS LA VALEUR : le hook PUBLIE desormais sa taille (`ringMax`). Ce 200 ne
#: sert que face a un hook anterieur, et le probe DIT alors qu'il l'a suppose.
RING = 200

#: Le seed du `rl_duel build`, EXPLICITE et parametrable (#477-r28). Il gouverne le RNG du match
#: et, roster non impose, le tirage des unites : c'est lui qui rend deux passages COMPARABLES.
#: Mesure a poll serre : a seed fixe, NOTRE runner produit exactement 211 fires au `build` de
#: `C1_02` 2v2 et 73 a l'`aiturn` -- le corpus propre EST reproductible.
SEED = R19.SEED

#: Periode du poll continu de `Collecteur`. Le corpus reste COMPLET tant que le debit demeure sous
#: la taille du ring par periode ; au-dela, les `seq` manquants sont ENUMERES, jamais devines.
#: Mesure : a 0.10 s le `build` laissait 403 trous, a 0.02 s il en laisse 7. La latence RPC
#: (20-50 ms) borne le gain d'une periode plus courte -- le vrai remede est le ring elargi.
INTERVALLE = 0.02

#: Duree d'une sonde de SILENCE (`sonde_silence`).
SILENCE = 1.0

BOARDS_DEFAUT = ("MC1_67", "C1_02")
#: Le roster 2v2 crafte de #477-r21 : il tient sous le ring, la ou un 5v5 le deborde au build.
ROSTER_2V2 = ("adeptHospitaller,astraBullgryn", "blackTerminator,worldJakhal")

#: Les cinq mutants. DEUX d'entre eux (`comparaison_inversee`, `append_nu`) sont INERTES DES QUE
#: LES PRIORITES SONT UNIFORMES -- inertes PAR LES DONNEES, pas par construction : a priorites
#: egales `AddSorted` degenere exactement en `append`, et `compare_to` ne rend jamais -1. Ils sont
#: gardes pour que cette inertie soit MESUREE et DITE (`a_morde=false` + le compte d'exercice) au
#: lieu d'etre supposee ; le tri lui-meme est garde offline, avec des priorites heterogenes
#: (`tests/engine/test_477r21r2b_activation_cache_offline.py`).
MUTATIONS = ("ordre_de_creation_ignore", "insertion_en_tete", "sans_pre_peuplement",
             "comparaison_inversee", "append_nu")


# --------------------------------------------------------------------------- capture
class Fenetre:
    """Une fenetre de trace : les fires produits pendant UNE etape, et les `seq` qui MANQUENT.

    ⚠ `perdus` N'EST PLUS UNE SOUSTRACTION, et le changement n'est pas cosmetique. L'ancienne
    version calculait `attendus - len(fires)`, ce qui ADDITIONNE deux grandeurs de sens OPPOSE :
    un fire a nous evince du ring (une perte, qui doit compter) et un fire ETRANGER entre dans la
    fenetre (une contamination, qui fait GROSSIR `len(fires)` et donc RABAISSE le compte, jusqu'a
    l'annuler). Un corpus a la fois ampute et pollue pouvait ainsi s'annoncer `perdus 0`.
    Les `seq` du hook etant strictement croissants, l'ensemble attendu est l'intervalle
    `]depuis, total]` : ce qui manque s'ENUMERE au lieu de se deduire."""

    def __init__(self, etiquette: str, fires: List[dict], depuis: int, total: int,
                 tours: int = 0, duree: float = 0.0, ring: Optional[int] = None) -> None:
        #: la taille de ring PUBLIEE par le hook, ou `None` si le hook ne la publie pas.
        self.ring = ring
        self.etiquette = etiquette
        self.fires = sorted(fires, key=lambda f: int(f.get("seq") or 0))
        self.depuis = depuis
        self.total = total
        #: les unites APPARUES pendant CETTE fenetre (`None` = pas mesure). Le rattachement est
        #: par fenetre, et non au scenario : le corpus ne retient que les fenetres SANS TROU, donc
        #: un spawn survenu dans une fenetre ECARTEE n'est PAS dans ce qu'on mesure. L'attribuer au
        #: scenario ferait afficher « REGIME EXERCE » au-dessus d'un corpus qui ne le contient pas
        #: -- le vice meme que le tri-etat de ce probe existe pour interdire.
        self.spawns: Optional[List[int]] = None
        #: tours de poll EFFECTIVEMENT rendus pendant l'etape, et duree de l'etape. Les DEUX sont
        #: imprimes : un poll qui n'a rendu que ses deux tours d'encadrement sur une etape de
        #: plusieurs secondes ne s'est pas « fait doubler par le debit », il a ete BLOQUE -- et
        #: c'est une cause differente, qui appelle un remede different.
        self.tours = tours
        self.duree = duree
        vus = {int(f.get("seq") or 0) for f in fires}
        self.trous = [s for s in range(depuis + 1, total + 1) if s not in vus]
        self.perdus = len(self.trous)

    @property
    def attendus(self) -> int:
        return max(0, self.total - self.depuis)

    @property
    def mesuree(self) -> bool:
        """Une fenetre a trous N'EST PAS UNE MESURE -- elle n'est ni verte ni rouge."""
        return not self.trous


def lire_total(session: int) -> int:
    """`totalFires` seul -- le compteur GLOBAL du hook, tous runners confondus."""
    r = R15A.rpc(session, "triggerTrace", {"limit": 1})
    if not r.get("installed"):
        raise MesureImpossible("`triggerTrace` non installe -- le hook s'arme au register")
    return int(r.get("totalFires") or 0)


class Collecteur:
    """Poll CONTINU de `triggerTrace` pendant une etape. Aucun reset, aucun capteur neuf.

    C'EST LE CRAN QUI REND LE PROBE REPRODUCTIBLE (#477-r28). Le ring est un tampon PARTAGE de
    `RING` entrees que ce probe n'a pas le droit de vider (`triggerTraceReset` effacerait la trace
    des autres agents). Une lecture unique APRES l'etape ne peut donc voir que ses 200 derniers
    fires, et lesquels survivent depend du bruit des voisins : c'est ce qui faisait BASCULER le
    verdict entre deux passages du MEME commit (19 evenements / 24 ruptures / ROUGE, puis
    10 / 1 / VERT). Poller PENDANT l'etape ramene la perte a zero tant que le debit reste sous
    `RING` fires par periode, et la rend VISIBLE sinon."""

    def __init__(self, session: int, intervalle: float = INTERVALLE) -> None:
        self.session = session
        self.intervalle = intervalle
        self.fires: Dict[int, dict] = {}
        self.total = 0
        self.depuis = 0
        self.tours = 0
        #: taille du ring telle que le HOOK la publie -- `None` tant qu'aucun tour n'a repondu,
        #: et tri-etat ensuite : `ring_publie is None` = hook anterieur, on RETOMBE sur `RING` en
        #: le disant. Deviner cette valeur ferait lire 5 % d'un ring elargi en se croyant complet.
        self.ring_publie: Optional[int] = None
        self.erreur: Optional[BaseException] = None
        self._stop = threading.Event()
        self._th: Optional[threading.Thread] = None

    @property
    def ring(self) -> int:
        return self.ring_publie if self.ring_publie else RING

    def _tour(self) -> None:
        r = R15A.rpc(self.session, "triggerTrace", {"limit": self.ring}, 60)
        if not r.get("installed"):
            raise MesureImpossible("`triggerTrace` non installe -- le hook s'arme au register")
        rm = r.get("ringMax")
        self.ring_publie = int(rm) if isinstance(rm, (int, float)) and rm else None
        self.total = int(r.get("totalFires") or 0)
        self.tours += 1
        for f in (r.get("recent") or []):
            self.fires[int(f.get("seq") or 0)] = f

    def _boucle(self) -> None:
        while not self._stop.is_set():
            try:
                self._tour()
            except BaseException as e:                   # noqa: BLE001 -- rendue a l'appelant
                self.erreur = e
                return
            self._stop.wait(self.intervalle)

    def __enter__(self) -> "Collecteur":
        self._tour()                    # amorce SYNCHRONE : `depuis` est pose AVANT l'etape
        self.depuis = self.total
        self.tours = 0
        self._t0 = time.time()
        self._th = threading.Thread(target=self._boucle, daemon=True)
        self._th.start()
        return self

    def __exit__(self, *exc) -> bool:
        self._stop.set()
        self.duree = time.time() - self._t0
        if self._th is not None:
            self._th.join(timeout=30)
        if self.erreur is None:
            try:
                self._tour()            # dernier tour : ce qui a suivi le dernier poll
            except BaseException as e:  # noqa: BLE001
                self.erreur = e
        return False

    def fenetre(self, etiquette: str) -> Fenetre:
        if self.erreur is not None:
            raise MesureImpossible("collecte `%s` interrompue : %s" % (etiquette, self.erreur))
        return Fenetre(etiquette, [f for s, f in self.fires.items() if s > self.depuis],
                       self.depuis, self.total, self.tours, self.duree, self.ring_publie)


def unites(session: int, rid: int) -> Optional[set]:
    """L'ensemble des `squadId` d'unites VIVANTES du match, ou `None` si la lecture a echoue.

    Sert au CONSTAT DE REGIME de #477-r27 : le residu suppose qu'une unite APPARUE en cours de
    partie divergerait, son identifiant depassant ceux des entites d'effet deja creees. Un
    scenario ou RIEN n'apparait n'exerce donc pas cet axe -- et un (I5) vert y serait le meme
    vert qui ne mesure rien que le probe denonce deja pour les suites a moins de deux porteurs
    communs. On CONSTATE le spawn, on ne le suppose pas du roster."""
    try:
        ob = R15A.rpc(session, "observeBattle", {"runnerId": rid}, 60)
    except MesureImpossible:
        return None
    if not ob:
        return None
    return {u.get("squadId") for u in (ob.get("units") or []) if u.get("squadId") is not None}


def sonde_silence(session: int, duree: float = SILENCE) -> int:
    """Le ring bouge-t-il PENDANT QUE NOTRE RUNNER EST INERTE ? Rend le nombre de fires apparus.

    C'est le SEUL discriminant de CONTAMINATION disponible sans capteur neuf. Le hook n'emet aucun
    identifiant de runner, et les identifiants d'entite sont attribues PAR MATCH -- mesure du
    2026-08-06 : deux runners du meme board portent tous deux `49`/`51`, donc AUCUN champ d'un fire
    ne dit de quelle bataille il vient, et filtrer par « nos » entites ne separerait rien. Ce qu'on
    peut etablir, c'est qu'un fire apparait a un instant ou NOUS ne jouons rien : celui-la est
    ETRANGER sans ambiguite.

    ⚠ SENS UNIQUE, ET C'EST DECLARE : un delta non nul PROUVE la contamination ; un delta nul ne
    prouve PAS son absence -- un voisin peut avoir tire pendant notre etape et s'etre tu pendant la
    sonde. Le probe ne rend donc jamais « corpus propre », il rend « aucune activite etrangere
    DETECTEE par N sonde(s) de M s », en imprimant N et M. Meme discipline que le tri-etat
    d'`host_inputs.py` : ne jamais rendre pour une MESURE ce qui n'est qu'une ABSENCE DE SIGNAL."""
    t0 = lire_total(session)
    time.sleep(duree)
    return max(0, lire_total(session) - t0)


def registre_du_port(session: int, rid: int) -> Optional[Dict[int, List[int]]]:
    """L'ORDRE que le registre du PORT rendrait, par `EventTriggerType` -- ou `None` si l'etat
    n'a pas pu etre charge.

    C'est la CONFRONTATION qui donne son sens a la tranche : `engine/runner/operations/triggers/
    dispatch/core.py::evaluate_trigger_operation` RECONSTRUIT son registre a chaque evenement,
    par concatenation `abilities(par entite) + globals + effets(par unite)`, la ou le natif LIT
    une liste persistante `active[trigger]`. Les deux ordres n'ont aucune raison structurelle de
    coincider ; ce probe mesure s'ils coincident EN FAIT.

    On compare la suite des IDENTIFIANTS D'ENTITE DISTINCTS CONSECUTIFS -- pas les classes : le
    port n'a pas le FQN natif, et 86 classes portees ne couvrent qu'une fraction du registre
    natif. Un sous-ensemble ne peut pas contredire une suite dont il ne voit qu'une partie ;
    la suite des porteurs, elle, se compare."""
    try:
        dv = R15A.rpc(session, "decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = R15A.rpc(session, "observeBattle", {"runnerId": rid}, 60)
        snap = R15A.rpc(session, "combatSnapshot", {"runnerId": rid}, 90)
    except MesureImpossible:
        return None
    if not dv or not ob:
        return None
    from engine.runner.snapshot import load_state
    from engine.runner.operations.triggers.dispatch.core import (
        collect_effect_triggers, collect_global_triggers, collect_triggered_abilities)

    try:
        st = load_state(dv, ob, snap, board=None)
    except Exception:                                    # noqa: BLE001 -- montage, pas mesure
        return None
    registre = (collect_triggered_abilities(st) + collect_global_triggers()
                + collect_effect_triggers(st))
    par_event: Dict[int, List[int]] = {}
    for e in registre:
        ids = {int(e.event_id)} | {int(x) for x in getattr(e, "event_ids", ()) or ()}
        for ev in ids:
            if ev < 0 or e.owner_id is None:
                continue
            suite = par_event.setdefault(ev, [])
            if not suite or suite[-1] != int(e.owner_id):
                suite.append(int(e.owner_id))
    return par_event


def capturer(session: int, board: str, tours: int, p_units: str, a_units: str,
             seed: int = SEED, intervalle: float = INTERVALLE,
             silence: float = SILENCE) -> Tuple[List[Fenetre], int,
                                                Optional[Dict[int, List[int]]], int, int,
                                                Optional[List[int]]]:
    """Monte un runner, joue `tours` tour(s), rend les fenetres de trace de CHAQUE etape.

    Chaque etape est encadree par un `Collecteur` (poll continu, aucune perte tant que le debit
    tient) et suivie d'une `sonde_silence` -- notre runner etant alors inerte, tout fire qui
    apparait est ETRANGER. Rend `(fenetres, runnerId, registre_du_port, fires_etrangers, sondes)`.

    ⚠ LA SONDE PASSE AVANT `registre_du_port` : celui-ci appelle `decisionView`/`combatSnapshot`,
    qui font tourner du natif et donc peuvent tirer des `ShouldTrigger`. Sonder apres imputerait
    a un voisin ce que le probe a lui-meme produit."""
    state = OUT / ("state-477r21r2b-%s.json" % board)
    state.parent.mkdir(parents=True, exist_ok=True)
    fenetres: List[Fenetre] = []
    etrangers, sondes = sonde_silence(session, silence), 1
    with Collecteur(session, intervalle) as c:
        rid = R19.build(board, state, p_units, a_units, seed=seed)
    fenetres.append(c.fenetre("build"))
    try:
        # Les lectures du CONSTAT DE REGIME encadrent CHAQUE tour, et chacune est faite AVANT la
        # sonde qui suit : leurs propres fires sont ainsi deja comptes quand la sonde lit son
        # `total` de depart, donc jamais imputes a un voisin.
        avant_u = unites(session, rid)
        etrangers += sonde_silence(session, silence)
        sondes += 1
        for i in range(tours):
            with Collecteur(session, intervalle) as c:
                q = subprocess.run([sys.executable, "rl_duel.py", "aiturn",
                                    "--state-file", str(state)],
                                   cwd=str(HERE), capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=900)
            w = c.fenetre("aiturn-%d" % (i + 1))
            apres_u = unites(session, rid)
            # tri-etat : `None` = pas mesure (une lecture a echoue), jamais une liste vide.
            w.spawns = (sorted(apres_u - avant_u)
                        if avant_u is not None and apres_u is not None else None)
            avant_u = apres_u
            fenetres.append(w)
            etrangers += sonde_silence(session, silence)
            sondes += 1
            if q.returncode != 0:
                break
        port = registre_du_port(session, rid)
    finally:
        R15A.dispose(state)
    if not any(f.fires for f in fenetres):
        raise MesureImpossible("`triggerTrace` n'a rendu AUCUN fire -- hook muet ou ring sature "
                               "par un autre agent")
    return fenetres, rid, port, etrangers, sondes


# --------------------------------------------------------------------------- decoupe en passes
def cle(f: dict) -> tuple:
    """L'identite d'une ENTREE du cache, telle que la trace la rend.

    `(ownerId, rawType, cls)` -- les trois ensemble, jamais l'un seul : une meme `configId` rend
    PLUSIEURS `ITriggeredAbility` (`IAbilitiesDatabase` slot 2 rend une LISTE), donc `1142` occupe
    deux entrees distinctes que seul le FQN de classe separe."""
    return (f.get("ownerId"), f.get("rawType"), f.get("cls"))


def passes(fires: List[dict], event: int) -> List[List[dict]]:
    """Les PASSES de parcours d'`active[event]`, decoupees a chaque retour sur la 1re cle.

    ⚠ ON NE DECOUPE PAS SUR LE CHANGEMENT D'`event` : le natif IMBRIQUE (un trigger qui firent
    publie d'autres evenements, dont les fires s'intercalent). La trace mesuree le montre --
    `SpecificAbilityInit` interrompu par des `EffectAdded` puis repris. Decouper sur l'evenement
    couperait une passe en deux et fabriquerait une fausse instabilite."""
    seq = [f for f in fires if int(f.get("event") or -1) == int(event)]
    if not seq:
        return []
    k0 = cle(seq[0])
    out: List[List[dict]] = []
    cur: List[dict] = []
    for f in seq:
        if cle(f) == k0 and cur:
            out.append(cur)
            cur = []
        cur.append(f)
    out.append(cur)
    return out


def passe_modale(ps: List[List[dict]]) -> Tuple[Optional[List[dict]], int, int]:
    """La passe la plus frequente, son compte, et le nombre de passes COMPLETES.

    Une passe est dite complete si elle a la longueur MAXIMALE observee : les passes plus courtes
    sont des troncatures (debut evince du ring, ou fin coupee par la lecture)."""
    if not ps:
        return None, 0, 0
    lmax = max(len(p) for p in ps)
    completes = [p for p in ps if len(p) == lmax]
    compte: Dict[tuple, int] = {}
    for p in completes:
        compte[tuple(cle(f) for f in p)] = compte.get(tuple(cle(f) for f in p), 0) + 1
    meilleure = max(compte, key=lambda k: compte[k])
    modele = next(p for p in completes if tuple(cle(f) for f in p) == meilleure)
    return modele, compte[meilleure], len(completes)


# --------------------------------------------------------------------------- les invariants
def i1_stabilite(ps: List[List[dict]]) -> Tuple[int, int]:
    """(passes completes confrontees, divergentes). Non exerce si < 2 passes completes."""
    modele, n_modele, n_completes = passe_modale(ps)
    if modele is None or n_completes < 2:
        return (n_completes, 0)
    return (n_completes, n_completes - n_modele)


def i4_croissance(ps: List[List[dict]], modele: List[dict]) -> Tuple[int, int, int]:
    """(passes plus COURTES que la modale, celles qui en sont un PREFIXE, celles qui n'en sont
    meme pas une SOUS-SEQUENCE).

    ⚠ C'EST L'INVARIANT QUI DISCRIMINE LES DEUX CAUSES D'UNE RUPTURE (I2), et sans lui le probe
    AFFIRMAIT une priorite qu'il n'a pas lue. Une entite qui apparait DEUX FOIS dans la liste, en
    tete et en queue, admet exactement deux explications :

      (a) PRIORITE -- les entrees de queue ont un `get_Priority` strictement inferieur, donc
          `AddSorted` les a poussees derriere tout le monde des leur insertion ;
      (b) AJOUT TARDIF -- elles ont ete inscrites par un SECOND appel (`RefreshEntity`, le seul
          site a passer `checkIfAlreadyExist: true`), APRES les entites suivantes, et `AddSorted`
          les a donc appendees a priorite EGALE. La garde `<AddAbility>b__0` explique alors
          pourquoi les entrees deja presentes de la meme entite ne sont PAS dupliquees.

    Les deux rendent la MEME sequence finale. Ce qui les separe est l'HISTOIRE : sous (b), une
    passe ANTERIEURE a l'ajout est un PREFIXE STRICT de la passe finale ; sous (a), toutes les
    passes sont identiques des la premiere. Le compte de passes plus courtes est donc le compte
    d'exercice de cette discrimination -- ZERO passe courte = INDISCRIMINE, et c'est dit."""
    cible = [cle(f) for f in modele]
    courtes = [p for p in ps if len(p) < len(modele)]
    prefixes = sum(1 for p in courtes if [cle(f) for f in p] == cible[:len(p)])
    non_sous_seq = 0
    for p in courtes:
        it = iter(cible)
        if not all(any(c == k for k in it) for c in [cle(f) for f in p]):
            non_sous_seq += 1
    return len(courtes), prefixes, non_sous_seq


def _sous_sequence(petite: List[int], grande: List[int]) -> bool:
    """`petite` est-elle une SOUS-SEQUENCE de `grande` (meme ordre relatif, trous permis) ?"""
    it = iter(grande)
    return all(any(x == y for y in it) for x in petite)


def _porteurs(passe: List[dict]) -> List[int]:
    """La suite des identifiants d'entite DISTINCTS CONSECUTIFS d'une passe -- l'axe sur lequel la
    sequence du port est comparable a celle du natif (cf. `registre_du_port`)."""
    out: List[int] = []
    for f in passe:
        o = f.get("ownerId")
        if o is None:
            continue
        if not out or out[-1] != int(o):
            out.append(int(o))
    return out


def i2_monotonie(passe: List[dict]) -> Tuple[int, List[str]]:
    """(couples consecutifs a entite DIFFERENTE, ruptures nommees).

    Le compte d'exercice est le nombre de couples ou les deux entites DIFFERENT : sur une passe
    d'un seul porteur, l'invariant n'a rien a trancher et le dire est le point."""
    exerces, ruptures = 0, []
    for a, b in zip(passe, passe[1:]):
        oa, ob = a.get("ownerId"), b.get("ownerId")
        if oa is None or ob is None or oa == ob:
            continue
        exerces += 1
        if int(ob) < int(oa):
            ruptures.append("entite %s (%s, raw=%s) APRES %s"
                            % (ob, (b.get("cls") or "").rsplit(".", 1)[-1], b.get("rawType"), oa))
    return exerces, ruptures


class _Ability:
    """Le minimum que `add_ability` lit d'une `ITriggeredAbility` : ses triggers et sa priorite."""

    def __init__(self, triggers, priority: int = 0) -> None:
        self.triggers = set(int(t) for t in triggers)
        self.priority = int(priority)


class _Composant:
    """`TriggeredAbilityComponent` : la `KeyedCollection` de `TriggeredAbilityConfigId`."""

    def __init__(self, config_ids) -> None:
        self.config_ids = list(config_ids)


class _Entite:
    """L'entite ECS vue par `AddEntity` : un id + son composant d'abilities."""

    def __init__(self, eid: int, config_ids) -> None:
        self.eid = int(eid)
        self.is_unit = True
        self.triggered_ability_component = _Composant(config_ids)
        self.effect_component = None

    def __eq__(self, other) -> bool:
        return isinstance(other, _Entite) and other.eid == self.eid

    def __hash__(self) -> int:
        return hash(self.eid)

    def __repr__(self) -> str:
        return "e%d" % self.eid


def i3_rederivation(passe: List[dict], event: int, mutation: str = "") -> List[tuple]:
    """Ce que le PORT rend pour `active[event]`, alimente par les seuls ENSEMBLES observes.

    CE QUI EST DONNE : pour chaque entite, la liste de ses abilities (leur ordre INTRA-entite est
    copie -- il vient d'`IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities`, non
    porte, cf. borne (c) de l'entete).

    CE QUI EST DERIVE : l'ORDRE INTER-ENTITE. Le port n'en recoit rien de la passe -- les entites
    lui sont presentees dans l'ordre de leur IDENTIFIANT ECS, qui est l'ordre de CREATION
    (`MatchComponent$$NextId` est monotone, #477-r21-r3), parce que c'est l'ordre dans lequel le
    natif appelle `AddEntity`. La sequence rendue doit alors egaler la sequence native.

    C'est bien la REGLE qui est mesuree, pas une recopie : la contre-epreuve
    `ordre_de_creation_ignore` alimente le cache dans l'ordre inverse et doit rougir."""
    par_entite: Dict[int, List[tuple]] = {}
    for f in passe:
        oid = f.get("ownerId")
        if oid is None:
            continue
        par_entite.setdefault(int(oid), []).append((f.get("rawType"), f.get("cls")))

    # Un `IAbilitiesDatabase` qui rend, pour chaque cle, la liste d'abilities observee.
    catalogue: Dict[tuple, List[_Ability]] = {}
    entites: List[_Entite] = []
    for oid, items in par_entite.items():
        cids = []
        for idx, (raw, _cls) in enumerate(items):
            k = (oid, idx)
            catalogue[k] = [_Ability({int(event)})]
            cids.append(_ConfigId(k, int(raw or 0)))
        entites.append(_Entite(oid, cids))

    with _muter(mutation):
        cache = AbilityAndEffectCache(effects_database=lambda t: None,
                                      abilities_database=lambda c: catalogue[c.key])
        if mutation == "sans_pre_peuplement":
            cache.active = {}              # le ctor ne pre-peuplerait plus le dictionnaire
        ordre = sorted(entites, key=lambda x: -x.eid if mutation == "ordre_de_creation_ignore"
                       else x.eid)
        for e in ordre:
            cache.add_entity(e)
        try:
            rendu = cache.get_active_triggered_abilities_and_effects(int(event))
        except KeyError:
            return []
    return [(s.entity.eid, s.order) for s in rendu]


class _ConfigId:
    """`TriggeredAbilityConfigId` -- `key` identifie l'entree du catalogue, `order` est le
    `TriggeredAbilityType` que `SortedTriggeredAbility.<+0x18>` porte."""

    def __init__(self, key: tuple, order: int) -> None:
        self.key = key
        self.order = int(order)


class _muter:
    """Contexte de mutation. LES MUTANTS PORTENT SUR LE MODULE PORTE, JAMAIS SUR L'INSTANCE.

    ⚠ CE DETAIL A DEJA FABRIQUE UN FAUX `a_morde=True`, ET C'EST POURQUOI IL EST ECRIT ICI. Une
    premiere version reaffectait `cache.add_ability_or_effect` sur l'instance ; `AbilityAndEffectCache`
    declare `__slots__`, donc l'affectation LEVE `AttributeError`, l'exception etait capturee par
    l'appelant et rendue comme un resultat different -- les CINQ mutations se declaraient
    mordantes sans avoir jamais mute quoi que ce soit. Patcher `add_sorted` au niveau du MODULE
    mord reellement : `add_ability_or_effect` le resout par son nom global."""

    def __init__(self, nom: str) -> None:
        self.nom = nom
        self._sauve = None

    def __enter__(self):
        from engine.runner.caches import ability_and_effect_cache as MOD

        self._mod = MOD
        if not self.nom or self.nom in ("ordre_de_creation_ignore", "sans_pre_peuplement"):
            return self                    # ces deux-la portent ailleurs (ordre d'appel / ctor)
        self._sauve = MOD.add_sorted
        if self.nom == "comparaison_inversee":
            def add(value, lst):
                idx = -1
                for i, x in enumerate(lst):
                    if value.compare_to(x) == -1:          # sens INVERSE du natif
                        idx = i
                        break
                lst.insert(len(lst) if idx < 0 else idx, value)
        elif self.nom == "insertion_en_tete":
            def add(value, lst):
                lst.insert(0, value)
        elif self.nom == "append_nu":
            def add(value, lst):
                lst.append(value)
        else:
            raise MesureImpossible("mutation inconnue : %s" % self.nom)
        MOD.add_sorted = add
        return self

    def __exit__(self, *exc) -> bool:
        if self._sauve is not None:
            self._mod.add_sorted = self._sauve
        return False


# --------------------------------------------------------------------------- scenario
def scenario_une_fois(session: int, board: str, tours: int, p_units: str, a_units: str,
                      seed: int = SEED, intervalle: float = INTERVALLE,
                      silence: float = SILENCE) -> dict:
    fenetres, rid, port, etrangers, sondes = capturer(session, board, tours, p_units, a_units,
                                                      seed, intervalle, silence)
    # ⚠ LE CORPUS N'EST FAIT QUE DES FENETRES SANS TROU. Une fenetre amputee n'est pas « un peu
    # moins de donnees » : les passes y sont coupees arbitrairement, ce qui FABRIQUE des passes
    # courtes hors sous-sequence (I4) et des ruptures (I2) qui n'existent pas dans le natif.
    # L'ecarter est ce qui distingue « pas mesure » de « mesure a zero ».
    retenues = [w for w in fenetres if w.mesuree]
    tous = [f for w in retenues for f in w.fires]
    perdus = sum(w.perdus for w in fenetres)
    # ⚠ LE REGIME SE LIT SUR LES FENETRES RETENUES, PAS SUR LE SCENARIO. Mesure du 2026-08-06 : le
    # roster 5v5 spawne au TOUR 2, dont la fenetre deborde le ring et est donc ECARTEE, tandis que
    # le tour 1 -- seule fenetre retenue -- n'en contient aucun. Rattacher les spawns au scenario
    # affichait « REGIME EXERCE » au-dessus d'un corpus qui n'en portait aucune trace.
    if any(w.spawns is None for w in retenues):
        apparues = None                             # tri-etat : une lecture a manque
    else:
        apparues = sorted({u for w in retenues for u in (w.spawns or ())})
    evenements = sorted({int(f.get("event") or -1) for f in tous})

    # Les DEUX causes de non-mesure, nommees separement -- elles n'ont ni la meme portee ni le
    # meme remede. Un corpus vide de fenetres retenues n'est pas un corpus.
    causes: List[str] = []
    if etrangers:
        causes.append("CONTAMINATION AVEREE : %d fire(s) etranger(s) vu(s) alors que ce runner "
                      "etait inerte (%d sonde(s) de %.1f s). Le ring est partage et n'emet aucun "
                      "identifiant de runner : ces fires sont dans le corpus et rien ne les en "
                      "distingue." % (etrangers, sondes, silence))
    if not retenues:
        causes.append("AUCUNE fenetre sans trou : le poll continu n'a pas suivi le debit.")

    res = {"board": board, "runner": rid, "fenetres": fenetres, "retenues": len(retenues),
           "fires": len(tous), "perdus": perdus, "etrangers": etrangers, "sondes": sondes,
           "silence": silence, "seed": seed, "causes": causes, "mesure": not causes,
           "apparues": apparues,
           "evenements": [], "mutations": [], "port_charge": port is not None}
    for ev in evenements:
        ps = passes(tous, ev)
        modele, _n, n_completes = passe_modale(ps)
        if modele is None:
            continue
        completes, divergentes = i1_stabilite(ps)
        exerces, ruptures = i2_monotonie(modele)
        courtes, prefixes, non_sous_seq = i4_croissance(ps, modele)
        attendu = [(f.get("ownerId"), f.get("rawType")) for f in modele
                   if f.get("ownerId") is not None]
        rendu = i3_rederivation(modele, ev)
        # (I3) NE S'APPLIQUE QUE SI L'HISTOIRE DES APPELS EST SANS TRACE OBSERVABLE, c'est-a-dire
        # si (a) chaque entite forme un BLOC CONTIGU et (b) l'ordre inter-entite est MONOTONE.
        # Le port est alimente par UN appel `AddEntity` par entite, dans l'ordre des identifiants ;
        # des que le natif a inscrit en DEUX temps (cf. (I4)) -- bloc dedouble OU bloc remonte
        # devant un aine -- reproduire la sequence exige la SEQUENCE D'APPELS, entree declaree non
        # portee. Compter ces cas comme des ROUGES accuserait le port d'un manque qu'il DECLARE.
        # ⚠ LE SEUL CRITERE `bloc_contigu` NE SUFFISAIT PAS, et la mesure l'a montre :
        # `UnitFinishedTurn` sur C1_02 rend `[67, 53, 53, 53, 53]` -- deux blocs contigus, mais le
        # cadet passe DEVANT son aine. La rupture (I2) est la meme cause ; le critere doit donc
        # porter sur les DEUX.
        vus, bloc_contigu, prec = set(), True, None
        for o in (f.get("ownerId") for f in modele):
            if o != prec:
                if o in vus:
                    bloc_contigu = False
                vus.add(o)
                prec = o
        bloc_contigu = bloc_contigu and not ruptures
        res["evenements"].append({
            "event": ev, "nom": _nom_event(ev), "longueur": len(modele), "passes": len(ps),
            "completes": completes, "divergentes": divergentes,
            "i2_exerces": exerces, "i2_ruptures": ruptures,
            "i4_courtes": courtes, "i4_prefixes": prefixes, "i4_non_sous_seq": non_sous_seq,
            "bloc_contigu": bloc_contigu,
            "i3_ok": rendu == attendu, "i3_longueur": len(attendu),
            "i3_rendu": rendu, "i3_attendu": attendu,
            "i5_port": (port or {}).get(ev), "i5_natif": _porteurs(modele),
        })

    # Contre-epreuves : sur l'evenement au corpus le plus LARGE (celui qui a le plus de couples
    # inter-entite -- les autres ne peuvent rien discriminer).
    # La cible doit etre un evenement AU REGIME APPLICABLE (chaque entite en un bloc contigu) :
    # muter contre un rendu deja faux ne mesurerait rien.
    cible = max([e for e in res["evenements"] if e["bloc_contigu"]],
                key=lambda e: (e["i2_exerces"], e["longueur"]), default=None)
    if cible is not None:
        modele = next(p for p in [passe_modale(passes(tous, cible["event"]))[0]] if p)
        attendu = cible["i3_attendu"]
        for nom in MUTATIONS:
            try:
                rendu = i3_rederivation(modele, cible["event"], mutation=nom)
            except Exception as e:                       # noqa: BLE001 -- une mutation peut lever
                rendu = [("EXCEPTION", type(e).__name__)]
            a_morde = rendu != cible["i3_rendu"]
            res["mutations"].append((nom, a_morde, rendu != attendu, cible["nom"],
                                     cible["i2_exerces"]))
    return res


def empreinte(res: dict) -> Dict[str, tuple]:
    """TOUT ce qui ENTRE dans le verdict d'un passage, canonicalise, par TERME NOMME.

    Sert au seul critere EXACT de proprete du corpus dont ce probe dispose (cf. `scenario`). La
    portee est prise LARGE a dessein -- une liste de champs choisis ne peut pas montrer le champ
    qu'elle a oublie -- mais elle s'arrete a ce qui PESE dans le verdict, et le reglage de cette
    frontiere a ete impose par la mesure :

    ⚠ `len(fires)` D'UNE FENETRE ECARTEE N'EN FAIT PAS PARTIE, et l'y avoir mis a rendu DEUX
      scenarios `NON REPRODUCTIBLE` alors que leurs comptes PRODUITS etaient rigoureusement egaux
      (`build 1333 / aiturn 202` des deux cotes). Combien de fires un poll parvient a lire d'une
      fenetre qu'on va de toute facon ECARTER est un alea d'ordonnancement, pas une propriete du
      corpus : le faire peser accuse de pollution deux passages qui n'en portent aucune trace.

    Ce qui EST retenu de chaque fenetre : son nombre de fires PRODUITS (`attendus`) -- c'est LUI
    le detecteur, car il compte aussi les fires ETRANGERS -- et le fait qu'elle soit mesuree."""
    return {
        "fenetres": tuple((w.etiquette, w.attendus, w.mesuree) for w in res["fenetres"]),
        "evenements": tuple(
            (e["nom"], e["longueur"], e["passes"], e["completes"], e["divergentes"],
             e["i2_exerces"], tuple(e["i2_ruptures"]), e["i4_courtes"], e["i4_prefixes"],
             e["i4_non_sous_seq"], e["bloc_contigu"], e["i3_ok"], e["i3_longueur"],
             tuple(e["i5_port"] or ()), tuple(e["i5_natif"]))
            for e in res["evenements"]),
        "mutations": tuple((m[0], m[1], m[2]) for m in res["mutations"]),
        # le REGIME exerce fait partie de ce qui pese : deux passages dont l'un a vu un spawn et
        # l'autre non ne mesurent pas la meme chose, et le vert de l'un ne couvre pas l'autre.
        "apparues": tuple(res.get("apparues") or ()),
    }


def _termes_divergents(a: Dict[str, tuple], b: Dict[str, tuple]) -> List[str]:
    """Les TERMES qui different, nommes. Un « les empreintes different » sans dire OU fait
    piloter a l'aveugle -- c'est ce qui a fait chercher une pollution la ou il n'y en avait pas."""
    return sorted(k for k in a if a[k] != b.get(k))


def scenario(session: int, board: str, tours: int, p_units: str, a_units: str,
             seed: int = SEED, intervalle: float = INTERVALLE, silence: float = SILENCE,
             repetitions: int = 2) -> dict:
    """Joue le scenario `repetitions` fois et n'en rend une MESURE que si elles CONCORDENT.

    ⚠ C'EST LE SEUL CRITERE EXACT DISPONIBLE, ET LA MESURE A DU L'IMPOSER. La `sonde_silence`
    detecte une contamination quand elle tombe dessus, mais elle n'echantillonne que quelques
    secondes sur une trentaine : mesure du 2026-08-06, un scenario a rendu `0 fire etranger` a ses
    trois sondes ET 23 evenements / 15 ruptures / 5 passes hors sous-sequence -- soit trois fois le
    corpus propre, donc massivement pollue, et un ROUGE qui n'accusait pas le port. C'est
    exactement le faux rouge que ce residu devait faire disparaitre.

    Ce qui tranche vraiment : a seed fixe, NOTRE runner produit un nombre DETERMINISTE de fires
    (mesure : 211 au `build` de `C1_02` 2v2 et 73 a l'`aiturn`, reproduits a deux instants
    differents). Deux passages qui CONCORDENT sur toute l'empreinte n'ont donc pas ete pollues ;
    deux passages qui divergent l'ont ete, et on ne sait pas lequel -- donc AUCUN n'est retenu.

    ⚠ SENS UNIQUE, LUI AUSSI : la concordance ne PROUVE pas la proprete (deux passages pourraient
    subir la meme pollution), elle la rend improbable. Le probe rend « CONCORDANT sur N passage(s) »
    et imprime N, il ne rend jamais « corpus propre »."""
    passages = []
    for i in range(max(1, repetitions)):
        r = scenario_une_fois(session, board, tours, p_units, a_units, seed, intervalle, silence)
        r["passage"] = i + 1
        passages.append(r)
    base = passages[0]
    base["passages"] = len(passages)
    if len(passages) > 1:
        empreintes = [empreinte(p) for p in passages]
        discordants = [(p["passage"], _termes_divergents(empreintes[0], e))
                       for p, e in zip(passages[1:], empreintes[1:]) if e != empreintes[0]]
        base["concordant"] = not discordants
        if discordants:
            # ⚠ DEUX CAUSES, ET LES CONFONDRE SERAIT AFFIRMER CE QU'ON N'A PAS LU. Le nombre de
            # fires PRODUITS pendant une fenetre (`attendus`) compte aussi les etrangers :
            #   * `attendus` DIFFERENT  -> POLLUTION AVEREE, des fires etrangers ont traverse la
            #     fenetre d'un passage et pas de l'autre ;
            #   * `attendus` EGAUX      -> le corpus produit est le MEME (mesure : 211 au `build`
            #     de `C1_02` 2v2, 73 a l'`aiturn`, a chaque passage). Ce qui a bouge est ce que le
            #     poll a REUSSI A LIRE d'une fenetre qui deborde le ring -- un ALEA DE COLLECTE,
            #     pas une pollution. Les deux empechent de mesurer ; une seule accuse les voisins.
            produits = [tuple((w.etiquette, w.attendus) for w in p["fenetres"]) for p in passages]
            pollue = len(set(produits)) > 1
            base["causes"] = list(base["causes"]) + [
                "NON REPRODUCTIBLE (%s) : a seed IDENTIQUE (%d), le(s) passage(s) %s divergent du "
                "1er sur le(s) terme(s) %s. %s Fires PRODUITS par fenetre : %s"
                % ("POLLUTION AVEREE" if pollue else "ALEA DE COLLECTE",
                   base["seed"],
                   ", ".join(str(n) for n, _t in discordants),
                   ", ".join(sorted({t for _n, ts in discordants for t in ts})),
                   "Le ring est PARTAGE et les comptes PRODUITS different : des fires etrangers "
                   "ont traverse au moins un des deux passages, et rien ne dit lequel."
                   if pollue else
                   "Les comptes PRODUITS sont IDENTIQUES -- le corpus de ce runner est donc bien "
                   "deterministe, et ce qui a bouge est ce que le poll a pu lire d'une fenetre "
                   "qui deborde le ring. Remede : le ring elargi, pas un re-jeu.",
                   " | ".join("passage %d = %s"
                              % (p["passage"], [(w.etiquette, w.attendus) for w in p["fenetres"]])
                              for p in passages))]
            base["mesure"] = False
    else:
        base["concordant"] = None
    return base


def _nom_event(ev: int) -> str:
    try:
        return EventTriggerType(int(ev)).name
    except ValueError:
        return "<%d hors mirror>" % ev


def imprimer(res: dict) -> None:
    print("  runner %s : seed %d ; %d fire(s) RETENU(s) sur %d fenetre(s) mesuree(s) / %d"
          % (res["runner"], res["seed"], res["fires"], res["retenues"], len(res["fenetres"])))
    for w in res["fenetres"]:
        anneau = ("ring %d publie" % w.ring) if w.ring else ("ring SUPPOSE %d -- le hook ne le "
                                                             "publie pas" % RING)
        print("      fenetre %-10s %4d lu(s) / %4d produit(s)  %3d poll(s) en %5.1f s   %s%s"
              % (w.etiquette, len(w.fires), w.attendus, w.tours, w.duree,
                 "NON MESUREE -- %d seq manquant(s), %s" % (w.perdus, anneau)
                 if w.perdus else "complete",
                 ("   SPAWN %s" % w.spawns) if w.spawns else ""))
    print("      sonde(s) de silence : %d de %.1f s ; %d fire(s) etranger(s) DETECTE(s)%s"
          % (res["sondes"], res["silence"], res["etrangers"],
             "" if res["etrangers"] else " (absence de signal, PAS une preuve de proprete)"))
    if res.get("concordant") is None:
        print("      repetitions : 1 -- corpus NON CERTIFIE par concordance (`--repetitions 2`).")
    else:
        print("      repetitions : %d -- empreintes %s"
              % (res["passages"], "CONCORDANTES" if res["concordant"] else "DIVERGENTES"))
    ap = res.get("apparues")
    if ap is None:
        print("      REGIME SPAWN : NON MESURE -- l'inventaire des unites n'a pas pu etre lu.")
    elif ap:
        print("      REGIME SPAWN : EXERCE DANS LE CORPUS -- %d unite(s) apparue(s) pendant une "
              "fenetre RETENUE : %s" % (len(ap), ap))
    else:
        print("      REGIME SPAWN : NON EXERCE dans le corpus RETENU. Un (I5) vert ne dit donc "
              "RIEN de l'axe que #477-r27 met en cause.")
    for c in res["causes"]:
        print("      ! %s" % c)
    if not res["mesure"]:
        print("      => SCENARIO NON MESURE : ni vert ni rouge.")
        return
    print("  SEQUENCES par `EventTriggerType` (la passe MODALE de chaque ; (I5) `*` = exerce mais "
          "NON DISCRIMINANT, moins de 2 porteurs communs) :")
    for e in res["evenements"]:
        i3 = "OK" if e["i3_ok"] else ("ROUGE" if e["bloc_contigu"] else "HORS REGIME")
        print("      %-28s longueur %-3d passes %-3d completes %-3d "
              "(I1) divergentes %-3d  (I2) couples inter-entite %-3d ruptures %-2d  "
              "(I4) courtes %-3d dont prefixes %-3d  (I3) re-derive %s"
              % (e["nom"], e["longueur"], e["passes"], e["completes"], e["divergentes"],
                 e["i2_exerces"], len(e["i2_ruptures"]), e["i4_courtes"], e["i4_prefixes"], i3))
        for r in e["i2_ruptures"]:
            print("          (I2) RUPTURE : %s" % r)
            if e["i4_courtes"] == 0:
                print("              -> INDISCRIMINE : aucune passe plus courte dans ce corpus. "
                      "Les deux causes -- priorite < Normal, ou AJOUT TARDIF par `RefreshEntity` "
                      "-- rendent la meme sequence. Le probe ne tranche pas.")
            elif e["i4_prefixes"] == e["i4_courtes"]:
                print("              -> AJOUT TARDIF (cause (b)) : les %d passe(s) plus courte(s) "
                      "sont TOUTES des PREFIXES de la passe finale, donc la liste a GRANDI en "
                      "queue. Une priorite < Normal aurait donne la meme sequence DES la premiere "
                      "passe. La donnee manquante est la SEQUENCE D'APPELS, pas la priorite."
                      % e["i4_courtes"])
            else:
                print("              -> %d passe(s) courte(s), dont %d prefixes : la croissance "
                      "n'est pas purement en queue -- relire le detail."
                      % (e["i4_courtes"], e["i4_prefixes"]))
        if e["i4_non_sous_seq"]:
            print("          (I4) %d passe(s) courte(s) ne sont PAS des sous-sequences de la "
                  "modale -- le cache aurait ete REORDONNE, ce que ni `AddSorted` ni les retraits "
                  "ne font." % e["i4_non_sous_seq"])
        if e["i5_port"]:
            # ⚠ LE MEME CRITERE QUE LE VERDICT, ET C'EST TOUT LE POINT. Cette ligne comparait a
            # l'EGALITE pendant que le verdict, lui, compte par SOUS-SEQUENCE : `port=[77]` vs
            # `natif=[77, 81]` s'affichait donc `DIVERGENT` au-dessus d'un verdict qui n'y voyait
            # aucune divergence -- le port ne couvre qu'une fraction du registre natif, sa suite
            # est un SOUS-ENSEMBLE, et l'accuser a l'egalite est la faute deja corrigee au verdict
            # (4 divergences sur 5, dont 3 fausses). Deux criteres pour une meme grandeur, c'est un
            # lecteur qui croit voir un rouge la ou l'outil n'en compte pas.
            communs = [p for p in e["i5_port"] if p in e["i5_natif"]]
            etat = ("CONFORME" if _sous_sequence(communs, e["i5_natif"]) else "DIVERGENT")
            if len(communs) < 2:
                etat += "*"          # exerce mais NON DISCRIMINANT : une suite d'un seul porteur
            print("          (I5) registre du PORT %-10s port=%s natif=%s"
                  % (etat, e["i5_port"][:8], e["i5_natif"][:8]))
        if not e["i3_ok"]:
            print("          (I3) attendu %s" % (e["i3_attendu"][:12],))
            print("          (I3) rendu   %s" % (e["i3_rendu"][:12],))
            if not e["bloc_contigu"]:
                print("              -> HORS REGIME, pas ROUGE : la liste porte la trace d'une "
                      "inscription en DEUX TEMPS (bloc dedouble ou cadet devant son aine). "
                      "Reproduire cela exige la SEQUENCE D'APPELS `AddEntity` / `RefreshEntity`, "
                      "entree declaree non portee.")
    if not res["mutations"]:
        print("  CONTRE-EPREUVE : AUCUNE -- pas d'evenement au corpus exploitable.")
        return
    print("  CONTRE-EPREUVE (cible = `%s`, %d couple(s) inter-entite a mordre) :"
          % (res["mutations"][0][3], res["mutations"][0][4]))
    for nom, a_morde, rouge, _c, _n in res["mutations"]:
        print("      %-22s a_morde=%-5s rougit=%-5s %s"
              % (nom, a_morde, rouge, "OK" if (a_morde and rouge) else "ROUGE"))
        if not a_morde:
            print("          ! la mutation n'a PAS change ce qu'elle mute -- elle ne mesure "
                  "rien, quel que soit son verdict.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", type=int, default=None)
    ap.add_argument("--boards", default=",".join(BOARDS_DEFAUT))
    ap.add_argument("--tours", type=int, default=1)
    ap.add_argument("--p-units", default=ROSTER_2V2[0])
    ap.add_argument("--a-units", default=ROSTER_2V2[1])
    ap.add_argument("--sans-roster-large", action="store_true")
    ap.add_argument("--seed", type=int, default=SEED,
                    help="seed du `rl_duel build` -- fixe le RNG du match ET, roster non impose, "
                         "le tirage des unites. C'est lui qui rend deux passages comparables.")
    ap.add_argument("--intervalle", type=float, default=INTERVALLE,
                    help="periode du poll continu de `triggerTrace`, en secondes.")
    ap.add_argument("--silence", type=float, default=SILENCE,
                    help="duree d'une sonde de silence, en secondes (detection de contamination).")
    ap.add_argument("--repetitions", type=int, default=2,
                    help="passages par scenario. 2 = le corpus n'est retenu que si les deux "
                         "rendent la MEME empreinte a seed identique -- le seul critere EXACT de "
                         "non-pollution du ring PARTAGE. 1 desarme ce cran et le DIT.")
    args = ap.parse_args()

    try:
        session = args.session if args.session is not None else R15A.session_courante()
    except MesureImpossible as e:
        print("[477-r21-r2b] MESURE IMPOSSIBLE : %s" % e)
        return 2

    plans = [(b.strip(), args.p_units, args.a_units, b.strip())
             for b in args.boards.split(",") if b.strip()]
    if not args.sans_roster_large:
        # LE SCENARIO LARGE, et il n'est pas decoratif : sur le roster 2v2 l'invariant (I5) N'EST
        # PAS DISCRIMINANT (mesure -- aucune suite du port n'y atteint DEUX porteurs communs avec
        # le natif, donc aucune ne peut reveler un ordre faux). Le roster par defaut (5v5) est le
        # seul regime du corpus ou (I5) mord. Le garder en option ferait passer un vert qui ne
        # mesure rien pour une confrontation.
        plans.append(("C1_02", "", "", "C1_02-5v5"))
    print("[477-r21-r2b] session=%d  scenarios=%s  tours=%d  seed=%d  poll=%.2fs  silence=%.1fs "
          "repetitions=%d"
          % (session, ",".join(p[3] for p in plans), args.tours, args.seed,
             args.intervalle, args.silence, args.repetitions))
    resultats = []
    for board, pu, au, etiquette in plans:
        print("")
        print("=== SCENARIO %s ===" % etiquette)
        try:
            res = scenario(session, board, args.tours, pu, au,
                           args.seed, args.intervalle, args.silence, args.repetitions)
        except MesureImpossible as e:
            print("  MESURE IMPOSSIBLE : %s" % e)
            return 2
        res["board"] = etiquette
        resultats.append(res)
        imprimer(res)

    print("")
    print("=== VERDICT (corpus = %d board(s)) ===" % len(resultats))
    rc = 0
    for res in resultats:
        # ⚠ TRI-ETAT : un scenario NON MESURE ne compte NI dans le vert NI dans le rouge. Le
        # rabattre sur l'un ou l'autre est exactement la faute que ce cran repare -- un corpus
        # ampute rendait un (I4) ROUGE pour une cause etrangere au port, et un corpus contamine
        # aurait pu rendre un VERT sur des fires qui ne sont pas les notres.
        if not res["mesure"]:
            print("  %-8s NON MESURE -- %s" % (res["board"], res["causes"][0]))
            continue
        evs = res["evenements"]
        i1 = sum(e["divergentes"] for e in evs)
        i1_ex = sum(e["completes"] for e in evs)
        i2 = sum(len(e["i2_ruptures"]) for e in evs)
        i2_ex = sum(e["i2_exerces"] for e in evs)
        applicables = [e for e in evs if e["bloc_contigu"]]
        i3 = sum(1 for e in applicables if not e["i3_ok"])
        hors = len(evs) - len(applicables)
        i4_nss = sum(e["i4_non_sous_seq"] for e in evs)
        muets = [m[0] for m in res["mutations"] if not m[1]]
        print("  %-8s %2d evenement(s) ; (I1) %d divergente(s) / %d passe(s) complete(s) ; "
              "(I2) %d rupture(s) / %d couple(s) ; (I4) %d passe(s) courte(s) hors "
              "sous-sequence ; (I3) %d ROUGE / %d applicable(s) (+%d hors regime)"
              % (res["board"], len(evs), i1, i1_ex, i2, i2_ex, i4_nss, i3, len(applicables), hors))
        if muets:
            print("      MUTATIONS NON MORDANTES : %s -- inertes PAR LES DONNEES (priorites "
                  "uniformes) ; le tri est garde offline." % ", ".join(muets))
        # ROUGE si un mutant a bel et bien MUTE la sequence sans que la confrontation le voie.
        # ⚠ LE PORT NE COUVRE QU'UNE FRACTION DU REGISTRE NATIF (86 classes de triggers), DONC SA
        # SUITE EST UN SOUS-ENSEMBLE -- LA COMPARER A L'EGALITE L'ACCUSE A TORT. Mesure : une
        # premiere version rendait 4 divergences sur 5, dont TROIS n'etaient que des porteurs que
        # le port ne connait pas (`port=[49]` vs `natif=[53, 49]`). Le critere juste est la
        # SOUS-SEQUENCE : l'ORDRE RELATIF des porteurs communs doit etre le meme.
        # Les porteurs que le port inscrit et que le natif ne montre PAS sont comptes A PART :
        # `ShouldTrigger` n'est appelee qu'APRES `EvaluateTriggerOperation$$CanGetAbilityTrigger`,
        # donc une entree filtree en amont (owner mort, triggers desactives) est absente de la
        # trace sans etre absente du cache. Ce compte n'est donc pas un defaut d'ORDRE.
        i5_ex = [e for e in evs if e["i5_port"]]
        # ⚠ UNE SUITE D'UN SEUL PORTEUR NE PEUT PAS REVELER UN ORDRE FAUX. Le compte qui vaut est
        # celui des evenements ou le port rend AU MOINS DEUX porteurs distincts -- les autres sont
        # exerces sans etre DISCRIMINANTS, et le dire evite un vert qui ne mesure rien (meme cran
        # que le (I5) du volet A, `docs/rl/case-477r21r2a-gardes-refresh-effects.md` § 3).
        i5_disc = [e for e in i5_ex
                   if len([p for p in e["i5_port"] if p in e["i5_natif"]]) >= 2]
        i5_div = [e for e in i5_ex if not _sous_sequence(
            [p for p in e["i5_port"] if p in e["i5_natif"]], e["i5_natif"])]
        i5_inconnus = sorted({p for e in i5_ex for p in e["i5_port"]
                              if p not in e["i5_natif"]})
        if not res["port_charge"]:
            print("      (I5) NON MESURE -- l'etat du port n'a pas pu etre charge depuis le "
                  "runner. Ce n'est pas un zero : c'est une absence de mesure.")
        else:
            print("      (I5) registre du port : %d evenement(s) exerce(s) / %d, dont %d "
                  "DISCRIMINANT(s) (>= 2 porteurs COMMUNS) ; %d ordre(s) divergent(s)"
                  % (len(i5_ex), len(evs), len(i5_disc), len(i5_div)))
            if not i5_disc:
                print("           NON DISCRIMINE : aucune suite du port n'a 2 porteurs communs "
                      "avec le natif -- aucune ne peut reveler un ordre faux. Ce vert ne mesure "
                      "rien.")
            ap = res.get("apparues")
            print("           REGIME SPAWN (#477-r27) : %s"
                  % ("NON MESURE" if ap is None else
                     ("EXERCE -- unite(s) apparue(s) %s" % ap) if ap else
                     "NON EXERCE -- aucune unite apparue ; ce (I5) ne porte PAS sur l'axe du "
                     "residu, quel que soit son verdict"))
            if i5_inconnus:
                print("           %d porteur(s) inscrit(s) par le PORT et absent(s) de la trace "
                      "native : %s -- compte SEPARE, ce n'est pas un defaut d'ordre "
                      "(`CanGetAbilityTrigger` filtre en amont de `ShouldTrigger`)."
                      % (len(i5_inconnus), i5_inconnus[:10]))
            for e in i5_div:
                print("           ORDRE DIVERGENT %-28s port=%s natif=%s"
                      % (e["nom"], e["i5_port"][:8], e["i5_natif"][:8]))
        if i5_div:
            rc = 1
        aveugles = [m[0] for m in res["mutations"] if m[1] and not m[2]]
        if aveugles:
            print("      MUTATIONS MORDANTES NON VUES : %s -- la confrontation est AVEUGLE."
                  % ", ".join(aveugles))
        if i1 or i3 or i4_nss or aveugles:
            rc = 1
        if i2:
            print("      (I2) %d rupture(s) -- cf. le detail ci-dessus pour la cause "
                  "DISCRIMINEE par (I4). Ce n'est pas un echec du port." % i2)
    mesures = [r for r in resultats if r["mesure"]]
    print("  %d scenario(s) MESURE(s) / %d ; %d NON MESURE(s)"
          % (len(mesures), len(resultats), len(resultats) - len(mesures)))
    if not mesures:
        # Aucun corpus exploitable : ce n'est ni un VERT ni un ROUGE, et le rc doit le dire.
        print("  NON MESURE -- aucun scenario exploitable. Rien n'est confirme, rien n'est refute.")
        return 2
    print("  %s" % ("VERT" if rc == 0 else "ROUGE"))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
