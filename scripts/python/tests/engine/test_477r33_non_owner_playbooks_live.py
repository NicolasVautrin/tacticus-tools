"""GARDE #477-r33 -- trois `*NonOwnerPlaybook` natifs de plus au registre du port.

CE QUE CETTE GARDE PROTEGE, et pourquoi ce n'est pas de la dette mais un GISEMENT DE CONFONDS :

  * `1457 KardiocoreGalvanus` est **equipee AU SEED** sur `admecMarshall` ET `admecRuststalker`
    (`BC.Units[].TertiaryAbility = 1457`, niveau 1). Tout montage qui spawne l'une des deux
    heritait donc, cote NATIF, d'un `+20` sur les tuiles adjacentes a son porteur, sous le gate
    `UnitExtensions.IsMechanical(case.Unit)` -- pendant que le port rendait 0. C'est ce qui a rendu
    `#477-r31` ROUGE a sa premiere mesure (`X_nat = 30` pour `X_port = 10`) et l'a oblige a
    DESEQUIPER la relique pour mesurer sa propre feuille ;
  * `1461 BookOfFate` et `1495 NornCrown` sont des reliques de porteurs DU POOL (etat 2 de la
    ventilation des reliques : `--equip-relic`), donc armables par n'importe quel montage.

⚠ LE COMPTE DU RESIDU ETAIT FAUX, DE TROIS FACONS -- et c'est pourquoi l'etage 1 le RE-DERIVE au
lieu de le citer. Le residu annoncait « 13 des 25 `*NonOwnerPlaybook` », or :
  * `25` est un compte par NOM ; le filtre correct est le PARENT dans `frida/classes.tsv`
    (**28** concrets : 18 directs + 10 via `AdjacentToOwnerNonOwnerPlaybook<T>`) ;
  * la liste des « 13 » melangeait TROIS faces **ATTACK** (`ShieldOfFaith`, `WayOfTheShortBlade`,
    `NoHidingFromTheWatchers`), qui ne passent PAS par la feuille `TriggeredAbilitiesNonOwner(4)`
    cote MOUVEMENT, et oubliait les DEUX concrets sans suffixe (`CabalOfSorcerersPlaybook`,
    `WisdomOfTheAncientsPlaybook`) ;
  * elle attribuait `MastersOfManoeuvre` a `orksRuntherd`, dont la relique du seed est en realite
    `1475 SupaCyborkBody` -- laquelle n'a **aucun** playbook non-owner, donc **zero** confond.
Vraie ventilation : **24 MOVE / 3 ATTACK / 1 REPAIR**, et le decompte des confonds ARMES SANS
MONTAGE passe de **3 a 1** avec cette tranche (le dernier, `1064 FirstAmongTraitors` sur
`blackAbaddon`, est gate sur un trait `Chaos` qu'aucune unite du gameconfig ne porte).

LES TROIS CORPS, au decompile du build courant :

  `IdunBattle.AI.Playbook.Loki.KardiocoreGalvanusNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext`
      if (case.unit == null)                       { yield Fix64.Zero; yield break; }
      if (!UnitExtensions.IsMechanical(case.unit))   yield break;
      if (Query.<slot 0x60 = AreEntitiesAdjacent, arite 2>(owner, case.MovementTile))
          yield return GetUtilityValue("KardiocoreGalvanus_AdjacentFriendly");   // 20

  `IdunBattle.AI.Playbook.Loki.BookOfFateNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext`
      if (Query.<slot 0x60 = AreEntitiesAdjacent, arite 2>(owner, case.MovementTile))
          yield return GetUtilityValue("BookOfFate_AdjacentSummons");            // 5
      // AUCUN gate -- pas meme `case.unit == null`

  `IdunBattle.AI.Playbook.Loki.NornCrownNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext`
      if (case.unit == null) yield break;
      if (!HasTrait(case.unit, 0x3ea) && !HasTrait(case.unit, 0x2)) yield break;  // Psyker OU Summon
      units = Query.<slot 0x79 = GetSurroundingFriends, arite 4>(
                  case.unit, ToList(case.MovementTile), 2, true);
      if (Any(units, f => HasTrait(f, 0x7e8)))                                    // Synapse
          yield return GetUtilityValue("NornCrown_SummonsAndPsykers");            // 10

⚠ Le NOM d'un slot ne dit ni le camp ni la surcharge : `AreEntitiesAdjacent` occupe les slots
96/97/98 et `GetSurroundingFriends` les slots 119..122 selon l'arite. Ce sont les TYPES DES
ARGUMENTS au call-site qui fixent la surcharge -- faute deja commise deux fois dans cette lignee
(#477-r29 puis #477-r31).

CINQ MONTAGES, tous sur la geometrie `camp` de `probe_477r31` (zone plate, cible neutre au centre,
porteur ALLIE et porteur ENNEMI en miroir -- les deux bras sont donc observes A EGALITE par
`scorerTileTermTrace`, qui ne voit que le tier COMPARABLE) :
  * `kardio`         : le confond de #477-r31 devient le MESURANDE (relique NON retiree) ;
  * `kardio-gate`    : meme geometrie, carrier NON Mechanical -> le gate coupe, `X_nat = 0` ;
  * `bookoffate`     : `blackPossession` recoit `BookOfFate` des DEUX cotes ;
  * `norncrown`      : `tyranNeurothrope` recoit `NornCrown` des DEUX cotes, mover Psyker ;
  * `norncrown-gate` : meme montage, mover NI Psyker NI Summon.

Mesures fondatrices (`probe_477r33_non_owner_registry_gaps.py`, decomposition
`X = Tile(7) - Elevation - TileEffects` aux hooks EXISTANTS de `scorer-damage-trace`, armes pour UN
SEUL `aiStepDryRun` puis desarmes -- AUCUNE reinjection). AUCUNE de ces valeurs n'est gelee ici :
les assertions re-derivent tout de la mesure du pas.

⚠⚠ **CE FICHIER NE SE JOUE PAS EN PARALLELE DES AUTRES CONSOMMATEURS DE `scorerDamageTrace`.**
`scorerDamageTraceOn` / `scorerDamageTraceOff` sont des interrupteurs **SESSION-GLOBAUX** (seuls
les `*Dump` filtrent par `runnerId`). Deux processus pytest qui arment et desarment en meme temps
se coupent l'un l'autre : le perdant de la course mesure avec les hooks DESARMES, son `X_nat` est
tronque, et le rouge tombe sur un cas ALEATOIRE. La discipline de ce depot (« 4 fichiers en
parallele ») ne s'applique donc PAS a cette famille -- `test_477r29_rad_saturation_camp_live.py`,
`test_477r31_attract_mechanicals_camp_live.py` et ce fichier se jouent **SEQUENTIELLEMENT**
(une seule invocation pytest les enchaine tres bien : 83 verts en 107 s).

MESURE, pas suppose (2026-08-06, A/B a un seul facteur) :
  * bras A -- ce fichier + `test_433_r4_r3_r1_adjacent_to_owner_live.py` (qui n'arme PAS ces
    hooks), en parallele : **41 + 38 verts** ;
  * bras B -- ce fichier + `test_477r31_...` (qui les arme), en parallele : `477r31` tombe a
    **6 failed / 21 passed** ;
  * sequentiel, les trois fichiers : **83 verts**.
La contrainte est PRE-EXISTANTE et PARTAGEE : les deux fichiers voisins l'avaient deja avant cette
tranche, elle n'avait simplement jamais ete nommee. Un rouge de cette famille en passe parallele
n'accuse donc PAS le port -- le rejouer SEUL est le premier geste.

CE FICHIER NE PEUT PAS ETRE VERT SANS SON CAPTEUR, ET IL LE DIT DESORMAIS (2026-08-15).
`X_nat = Tile(7) - Elevation - TileEffects` exige les TROIS canaux de `scorer-damage-trace`. Le
jeu est passe au build `t6dpr4k06g` : le foyer live `frida/hooks/il2cpp/build-pin.ts` a REFUSE les
onze adresses epinglees de la session -- non pas parce que le build differait, mais parce que son
motif de forme codait en dur le suffixe `6c` et que ce build finit en `6g`, donc `installedBuild()`
rendait `null` (NON MESURABLE). `scorerTileTermTraceDump` survivait (il se resout au RUNTIME par
`resolveSharedPlaybookBody`), `scorerElevTraceDump` et `scorerLeafTraceDump` rendaient **0
entree**. Toutes les lignes sortaient a `x_nat = None`, `divergences` rendait 0 pour TOUS les
modeles -- y compris `ABSENT`, qui vaut pourtant 0.0 par construction -- et `test_le_natif_suit_le_
PORT` passait A VIDE : 12 F / 29 P, douze rouges qui accusaient les montages pour UNE panne de
capteur. `mesurer` refuse maintenant en NOMMANT la panne (`cause_x_nat_non_mesurable`), et le
verdict assertionne son propre non-vide. Le retour au VERT demande une FENETRE DE REINJECT.

ASCII only.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # tests/engine -> import du helper sibling

from counterproof import assert_sample_confrontable  # noqa: E402

import probe_477r33_non_owner_registry_gaps as P     # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
MAX_STEPS = 40

#: UN cas par montage, plus un SECOND couple board/seed pour le montage phare (`kardio`, le seul
#: dont le terme est arme SANS AUCUN montage). Le verdict ne tient donc ni a une geometrie ni a un
#: axe unique.
CASES = [("MC1_67", "777", "kardio"), ("C4_09", "31337", "kardio"),
         ("MC1_67", "777", "kardio-gate"), ("MC1_67", "777", "bookoffate"),
         ("MC1_67", "777", "norncrown"), ("MC1_67", "777", "norncrown-gate")]

#: les mutants que CHAQUE montage separe reellement. DERIVE du montage, pas recopie : un montage
#: dont le carrier franchit toujours le gate ne peut pas separer `SANS-GATE`, et un montage ou le
#: gate coupe rend TOUS les autres mutants inertes PAR ALGEBRE.
MUTANTS_ATTENDUS = {
    "kardio": ("CAMP-DEUX", "CAMP-ENNEMI", "ABSENT"),
    "kardio-gate": ("SANS-GATE",),
    "bookoffate": ("CAMP-DEUX", "CAMP-ENNEMI", "ABSENT"),
    "norncrown": ("CAMP-DEUX", "RAYON-1", "PRE-GATE-OFF", "ABSENT"),
    "norncrown-gate": ("SANS-GATE",),
}


@pytest.fixture(scope="module", params=CASES, ids=lambda c: "%s-%s-%s" % c)
def r33_case(request, rpc, build_runner):
    """La mesure du pas ou les DEUX bras du montage sont HOOKES, hooks armes UNE fois.

    Le montage vit dans le probe (`P._seed_bc_montage` + `P.build_extra` + `P.mesurer`, `call`
    INJECTE) : un seul foyer, deux consommateurs -- la garde ne re-code ni le seed BC (dont la pose
    de relique), ni les placements, ni la marche."""
    board, seed, montage = request.param
    tag = uuid.uuid4().hex[:8]
    seed_bc = ROOT / "logs" / "runners" / ("test477r33-seedbc-%s.json" % tag)
    P._seed_bc_montage(seed_bc, montage)
    extra = P.build_extra(board, montage)              # FOYER UNIQUE du montage (cf. le probe)
    extra[1] = str(seed_bc)
    rid = build_runner(seed, extra=extra, board=board)["rid"]
    mes = P.mesurer(lambda m, b, t=90: rpc(m, b, t), rid, montage, MAX_STEPS,
                    trace=lambda *_a: None)
    try:
        seed_bc.unlink()
    except OSError:
        pass
    return SimpleNamespace(rid=rid, mes=mes, montage=montage, board=board, seed=seed)


def _rows(r33_case) -> list:
    """Les lignes de la mesure, ou un ROUGE qui NOMME la panne au lieu d'un `KeyError`."""
    mes = r33_case.mes
    assert not mes.get("erreur"), (
        "aucune mesure (%s/%s/%s) : %s. Les gardes suivantes ne disent RIEN tant que ce point "
        "n'est pas regle (cf. `test_le_montage_a_bien_ete_mesure`)"
        % (r33_case.board, r33_case.seed, r33_case.montage, mes.get("erreur")))
    return mes["rows"]


# ---------------------------------------------------------------------------------------------
# ETAGE 1 -- offline : le RECENSEMENT, les cles, et les trois corps sur `ctx` synthetiques
# ---------------------------------------------------------------------------------------------
def test_le_recensement_est_RE_DERIVE_et_les_trois_ids_viennent_du_ctor():
    """Le compte ne se CITE pas : il se re-derive du PARENT, et l'id de chaque classe de son `.ctor`.

    Trois assertions, et c'est le TRIPLET qui porte le sens :
      * la famille compte bien 28 concrets, ventiles 24 MOVE / 3 ATTACK / 1 REPAIR -- si ce
        triplet bouge, c'est le BUILD qui a change et tout le reste du fichier est a relire ;
      * les trois entrees neuves sont au registre ET leur `ABILITY_ID` est celui que leur `.ctor`
        passe a la base (relu dans le binaire) -- pas un ordinal recopie ;
      * les faces ATTACK/REPAIR ne sont PAS au registre de la feuille MOUVEMENT : les y mettre
        ferait peser un terme d'ATTAQUE sur le sweep de deplacement."""
    from engine.playbook.non_owner import (NON_OWNER_MOVE_PLAYBOOKS, BookOfFateNonOwnerPlaybook,
                                           KardiocoreGalvanusNonOwnerPlaybook,
                                           NornCrownNonOwnerPlaybook)
    build = P._build_hash()
    concrets = P._concrets(build)
    faces = P._faces(build, concrets)
    ctors = P._ctor_ids(build, concrets)
    par_face = {}
    for n, fs in faces.items():
        for f in fs:
            par_face[f] = par_face.get(f, 0) + 1
    assert len(concrets) == 28, (
        "%d concrets derives du PARENT `TriggeredAbilityNonOwnerPlaybook`1` au lieu de 28 : le "
        "build a bouge, ou le filtre est retombe sur le NOM (le vice de #433-r4-r3-r1, re-commis "
        "par le residu #477-r33)" % len(concrets))
    assert (par_face.get("MOVE"), par_face.get("ATTACK"), par_face.get("REPAIR")) == (24, 3, 1), (
        "ventilation par FACE = %r au lieu de (24, 3, 1). ⚠ Les 10 concrets d'`AdjacentToOwner` "
        "n'ont AUCUN `Calculate*` a leur nom (corps gshared PARTAGE) : leur face se CREDITE depuis "
        "le parent, et chercher par leur nom rend l'ensemble vide" % (par_face,))
    for cls in (KardiocoreGalvanusNonOwnerPlaybook, BookOfFateNonOwnerPlaybook,
                NornCrownNonOwnerPlaybook):
        court = cls.__name__
        assert cls.ABILITY_ID in NON_OWNER_MOVE_PLAYBOOKS, (
            "%s n'est PAS au registre : `LoadPlaybookNonOwner` rendrait null cote port alors que le "
            "natif, lui, itere la paire -- c'est exactement le trou que cette tranche ferme" % court)
        assert ctors.get(court) == cls.ABILITY_ID, (
            "%s.ABILITY_ID = %r alors que son `.ctor` passe %r a la base. Un id faux n'ecrit ni "
            "erreur ni crash : il pose une entree MORTE ou ECRASE celle d'une autre ability (cf. "
            "`PrimarchOfTheFirstLegion`, #433-r4-r3-r1)" % (court, cls.ABILITY_ID, ctors.get(court)))
    hors = [n for n, fs in faces.items() if "MOVE" not in fs]
    dans = [n for n in hors if (ctors.get(n) in NON_OWNER_MOVE_PLAYBOOKS)]
    assert not dans, (
        "classe(s) SANS face MOVE inscrites au registre de la feuille MOUVEMENT : %r. Leur face est "
        "ATTACK ou REPAIR -- un autre dispatcher, un autre sweep" % (dans,))


def test_les_trois_cles_BC_sont_non_nulles_et_distinctes():
    """Les cles LUES au litteral (`probe_212_bc_key_literals.py`), confrontees au gameconfig VIVANT.

    Assertions dans les DEUX sens : chaque cle rend un poids non nul (sinon le terme serait plat et
    aucune mesure ne pourrait le contredire), et les trois sont DISTINCTES -- deux d'entre elles
    vivent dans la meme categorie `TriggeredAbilitiesNonOwner` avec des poids proches, donc seule la
    cle les separe."""
    from engine import weights as W
    from engine.playbook.non_owner import (BookOfFateNonOwnerPlaybook,
                                           KardiocoreGalvanusNonOwnerPlaybook,
                                           NornCrownNonOwnerPlaybook)
    wt = W.load()
    cles = [c.KEY for c in (KardiocoreGalvanusNonOwnerPlaybook, BookOfFateNonOwnerPlaybook,
                            NornCrownNonOwnerPlaybook)]
    assert len(set(cles)) == 3, "deux classes lisent la MEME cle BC : %r" % (cles,)
    for k in cles:
        w = wt.sub("TriggeredAbilitiesNonOwner", k)
        assert w, ("la cle `Utilities.Default.TriggeredAbilitiesNonOwner.%s` rend %r : le litteral "
                   "resolu au decompile a disparu du gameconfig" % (k, w))


def _terme(cls, tile, owner, ctx, wt):
    """Le terme rendu par UNE classe, appelee comme le dispatcher l'appelle (pre-gate deja passe)."""
    return cls().calculate_movement_utility_in_steps(tile, owner, True, ctx, wt)


def test_le_gate_de_KARDIOCORE_est_IsMechanical_et_PAS_HasTrait_Mechanical_nu():
    """Contre-epreuve offline : la difference est OBSERVABLE, et l'ignorer est SILENCIEUX.

    `IdunBattle.Entities.UnitExtensions$$IsMechanical` enchaine TROIS `HasTrait` en OU
    court-circuite (`Mechanical`, `LivingMetal`, `Vehicle`). Un `Vehicle` non `Mechanical` franchit
    donc le gate de 1457 -- la ou `NetherRealmCasketNonOwnerPlaybook`, qui teste `HasTrait
    (Mechanical)` NU, le refuse. Les deux classes cohabitent au registre : confondre les deux
    lectures ferait diverger l'une OU l'autre selon le mover, sans jamais lever."""
    from engine import weights as W
    from engine.playbook.non_owner import (KardiocoreGalvanusNonOwnerPlaybook as K,
                                           NetherRealmCasketNonOwnerPlaybook as N)
    from engine.entities.traits.unit_trait import UnitTrait
    wt = W.load()
    neigh = {(1, 1): [(1, 0), (1, 2), (0, 1), (2, 1), (0, 0), (2, 0)],
             (1, 0): [(1, 1), (0, 1), (2, 1), (0, 0), (2, 0), (1, 2)]}
    owner = {"pos": (1, 0), "id": 9}
    base = {"elev_by_pos": {}, "neigh_by_pos": neigh, "is_spawning": False}
    wk = float(wt.sub("TriggeredAbilitiesNonOwner", K.KEY))

    mech = dict(base, unit_traits=[int(UnitTrait.Mechanical)])
    assert _terme(K, (1, 1), owner, mech, wt) == wk, "un mover Mechanical adjacent doit valoir le poids"
    veh = dict(base, unit_traits=[int(UnitTrait.Vehicle)])
    assert _terme(K, (1, 1), owner, veh, wt) == wk, (
        "un mover `Vehicle` (0x405) ne franchit pas le gate : le port lit `HasTrait(Mechanical)` NU "
        "la ou le natif appelle `IsMechanical`, qui teste AUSSI LivingMetal et Vehicle")
    assert _terme(N, (1, 1), owner, veh, wt) == 0.0, (
        "`NetherRealmCasket` accepte un `Vehicle` : lui teste `HasTrait(Mechanical)` NU -- si les "
        "deux classes rendaient la meme chose, l'une des deux RE serait fausse")
    rien = dict(base, unit_traits=[])
    assert _terme(K, (1, 1), owner, rien, wt) == 0.0, "un mover sans trait mecanique doit rendre 0"
    loin = dict(base, unit_traits=[int(UnitTrait.Mechanical)])
    assert _terme(K, (2, 2), owner, loin, wt) == 0.0, (
        "une tuile NON adjacente au porteur rend le poids : le gate d'adjacence est absent")
    assert _terme(K, (1, 1), {"id": 9}, mech, wt) == 0.0, (
        "un porteur SANS position rend le poids : `AreEntitiesAdjacent` commence par ecarter "
        "l'entite sans tuile")
    assert _terme(K, (1, 1), owner, dict(mech, is_spawning=True), wt) == 0.0, (
        "le regime SPAWN (`case.unit == null`) rend le poids : le natif y yielde Fix64.Zero")


def test_BOOKOFFATE_n_a_AUCUN_gate_malgre_le_nom_de_sa_cle():
    """Le nom de cle (`BookOfFate_AdjacentSummons`) decrit l'INTENTION, pas la condition.

    Le corps natif ne lit JAMAIS `case.unit` : il n'y a ni `HasTrait(Summon)`, ni meme le
    `case.unit == null` que portent ses voisins. Lire le nom comme un gate ajouterait un filtre que
    le natif n'a pas -- et le terme disparaitrait pour tout mover non-summon, c'est-a-dire presque
    partout."""
    from engine import weights as W
    from engine.playbook.non_owner import BookOfFateNonOwnerPlaybook as B
    from engine.entities.traits.unit_trait import UnitTrait
    wt = W.load()
    neigh = {(1, 1): [(1, 0), (1, 2), (0, 1), (2, 1), (0, 0), (2, 0)]}
    owner = {"pos": (1, 0), "id": 9}
    w = float(wt.sub("TriggeredAbilitiesNonOwner", B.KEY))
    for traits in ([], [int(UnitTrait.Summon)], [int(UnitTrait.Hero)]):
        ctx = {"elev_by_pos": {}, "neigh_by_pos": neigh, "unit_traits": traits}
        assert _terme(B, (1, 1), owner, ctx, wt) == w, (
            "le terme depend des traits du mover (%r) : le corps natif n'en lit AUCUN" % (traits,))
    ctx = {"elev_by_pos": {}, "neigh_by_pos": neigh, "unit_traits": []}
    assert _terme(B, (2, 2), owner, ctx, wt) == 0.0, "une tuile non adjacente doit rendre 0"


def test_NORNCROWN_gate_DISJONCTIF_rayon_2_et_self_INCLUS():
    """Trois lectures qui ne se devinent pas, exercees separement.

    * le gate est une DISJONCTION `Psyker OU Summon` -- a l'inverse de `RelicOfLostCadia`, qui
      CONJUGUE `Imperial ET Summon` ; un port conjonctif rendrait 0 sur un Psyker non-summon ;
    * le disque est de RAYON 2 et PUREMENT geometrique (`IterateSurroundingTiles` n'a AUCUNE porte
      d'elevation) -- l'adjacence rendrait 0 a distance 2 ;
    * l'ACTEUR n'est PAS exclu de son propre voisinage : `GetSurroundingFriends(actor, ...)` ne
      retire jamais `actor`, et le mover est encore sur son ORIGINE pendant tout le sweep. C'est le
      volet que le montage live NE PEUT PAS exercer (son carrier n'est pas `Synapse` -- inertie
      declaree et assertionnee la-bas), donc il est EXERCE ici."""
    from engine import weights as W
    from engine.playbook.non_owner import NornCrownNonOwnerPlaybook as N
    from engine.entities.traits.unit_trait import UnitTrait
    wt = W.load()
    w = float(wt.sub("TriggeredAbilitiesNonOwner", N.KEY))
    owner = {"pos": (9, 9), "id": 9}          # la position du porteur est SANS EFFET sur ce terme
    syn = [UnitTrait.Synapse.name]
    base = {"elev_by_pos": {}, "neigh_by_pos": {}, "is_spawning": False, "self_pos": None,
            "enemy_units": []}

    # gate DISJONCTIF : Psyker seul, Summon seul, les deux -> le poids ; ni l'un ni l'autre -> 0.
    for traits in ([int(UnitTrait.Psyker)], [int(UnitTrait.Summon)],
                   [int(UnitTrait.Psyker), int(UnitTrait.Summon)]):
        ctx = dict(base, unit_traits=traits, friend_units=[{"pos": (1, 1), "traits": syn}])
        assert _terme(N, (1, 1), owner, ctx, wt) == w, (
            "gate refuse %r : le natif teste `Psyker` OU `Summon`, pas leur conjonction" % (traits,))
    ctx = dict(base, unit_traits=[int(UnitTrait.Hero)],
               friend_units=[{"pos": (1, 1), "traits": syn}])
    assert _terme(N, (1, 1), owner, ctx, wt) == 0.0, (
        "un mover NI Psyker NI Summon franchit le gate")

    # RAYON 2, pas 1 : un ami Synapse a distance 2 compte ; a distance 3, non.
    psy = [int(UnitTrait.Psyker)]
    d2 = dict(base, unit_traits=psy, friend_units=[{"pos": (3, 1), "traits": syn}])
    assert _terme(N, (1, 1), owner, d2, wt) == w, (
        "un ami Synapse a distance 2 ne compte pas : le port lit l'ADJACENCE la ou le call-site "
        "passe le litteral `2` a `GetSurroundingFriends`")
    d3 = dict(base, unit_traits=psy, friend_units=[{"pos": (4, 1), "traits": syn}])
    assert _terme(N, (1, 1), owner, d3, wt) == 0.0, (
        "un ami Synapse a distance 3 compte : le disque deborde le rayon 2")

    # le predicat est bien `Synapse`, et le camp est bien celui des AMIS.
    pas_syn = dict(base, unit_traits=psy,
                   friend_units=[{"pos": (1, 1), "traits": [UnitTrait.Psyker.name]}])
    assert _terme(N, (1, 1), owner, pas_syn, wt) == 0.0, (
        "un ami NON Synapse declenche le terme : le predicat natif est `HasTrait(f, 0x7e8)`")
    ennemi = dict(base, unit_traits=psy, friend_units=[],
                  enemy_units=[{"pos": (1, 1), "traits": syn}])
    assert _terme(N, (1, 1), owner, ennemi, wt) == 0.0, (
        "un ENNEMI Synapse declenche le terme : `GetSurroundingFriends` filtre les amis du MOVER")

    # SELF INCLUS -- le volet que le live ne peut pas exercer.
    self_syn = dict(base, unit_traits=[int(UnitTrait.Psyker), int(UnitTrait.Synapse)],
                    friend_units=[], self_pos=(2, 1))
    assert _terme(N, (1, 1), owner, self_syn, wt) == w, (
        "le MOVER Synapse, encore sur son origine a distance 1 de la tuile candidate, ne compte "
        "pas pour lui-meme : `GetSurroundingFriends(actor, ...)` n'exclut PAS `actor`")
    self_loin = dict(self_syn, self_pos=(5, 1))
    assert _terme(N, (1, 1), owner, self_loin, wt) == 0.0, (
        "le MOVER compte depuis une origine HORS du disque de rayon 2")
    assert _terme(N, (1, 1), owner, dict(self_syn, is_spawning=True), wt) == 0.0, (
        "le regime SPAWN (`case.unit == null`) rend le poids : le natif y fait `yield break`")


# ---------------------------------------------------------------------------------------------
# ETAGE 2 -- live
# ---------------------------------------------------------------------------------------------
def test_le_montage_a_bien_ete_mesure(r33_case):
    """ROUGE DE SCENARIO (#462-r6) : sans mesure, aucune des gardes suivantes ne dit rien."""
    assert_sample_confrontable(
        not r33_case.mes.get("erreur"),
        mutation="build %s/%s montage %r (seed BC : relique posee ou LAISSEE EN PLACE selon le "
                 "montage), puis marche de la trajectoire native jusqu'au pas ou les DEUX bras "
                 "sont HOOKES" % (r33_case.board, r33_case.seed, r33_case.montage),
        doit_casser="un pas ou les hooks `scorerTileTermTrace` couvrent les deux groupes de tuiles "
                    "du montage",
        observe=str(r33_case.mes.get("erreur")),
        remede="rejouer `python probe_477r33_non_owner_registry_gaps.py --board %s --seed %s "
               "--montage %s` : il imprime, pas par pas, le nombre de candidates et la taille des "
               "deux bras. Les hooks ne voient que les tuiles du tier COMPARABLE (les tuiles "
               "d'ATTAQUE) : si un bras est vide, c'est la geometrie qu'il faut re-etalonner"
               % (r33_case.board, r33_case.seed, r33_case.montage))


def test_les_deux_bras_sont_hookes(r33_case):
    """ROUGE DE SCENARIO : sans les DEUX bras, le mutant separateur n'est pas separable."""
    mes = r33_case.mes
    assert_sample_confrontable(
        bool(mes.get("bras_a")) and bool(mes.get("bras_b")),
        mutation="ventilation des tuiles HOOKEES par groupe du montage %r" % r33_case.montage,
        doit_casser="au moins une tuile par groupe (porteur/Synapse AMI seul, puis ENNEMI seul)",
        observe="bras_a=%s bras_b=%s" % (mes.get("bras_a"), mes.get("bras_b")),
        remede="cf. `test_le_montage_a_bien_ete_mesure`")


def test_le_natif_suit_le_PORT(r33_case):
    """LE VERDICT : `X_nat == X_port`, tuile par tuile, sur toutes les tuiles hookees.

    ATTENTION -- IL ASSERTIONNE SON PROPRE NON-VIDE, et ce n'est pas une precaution. `ecarts` saute les
    lignes dont `X_nat` vaut `None` -- la forme naturelle, puisqu'une tuile non hookee n'a rien a
    dire. Quand les TROIS canaux ne repondent pas, elles sont TOUTES a `None` et ce verdict rend
    VERT sur zero assertion evaluee. Mesure du 2026-08-15 : c'est exactement ce qui s'est produit
    quand le jeu est passe a `t6dpr4k06g` et que le foyer `build-pin` a refuse les adresses
    epinglees de `scorerElevTraceDump` / `scorerLeafTraceDump` -- 12 F / 29 P, et le fichier
    accusait ses montages. `mesurer` refuse desormais en amont (`cause_x_nat_non_mesurable`) ;
    ce cran-ci est le second verrou, pour qu'un changement de `mesurer` ne rouvre pas le trou en
    silence."""
    rows = _rows(r33_case)
    mesurees = [r for r in rows if r["x_nat"] is not None]
    assert mesurees, (
        "%d tuile(s) hookee(s), AUCUNE avec un `X_nat` calculable (%s/%s/%s). Ce verdict serait "
        "VERT sur zero assertion evaluee. `X_nat = Tile7 - Elevation - TileEffects` exige les "
        "TROIS canaux de `scorer-damage-trace` : lire `scorerDamageTraceOn.rvaHooks` et le RPC "
        "`nameResolutionStatus` (champ `pinnedAddressRefusals`) avant de conclure quoi que ce "
        "soit du port" % (len(rows), r33_case.board, r33_case.seed, r33_case.montage))
    ecarts = [(r["tile"], r["na"], r["ne"], r["x_nat"], r["x_port"], r["leaves"])
              for r in mesurees
              if abs(r["x_nat"] - r["x_port"]) > 1e-6]
    assert not ecarts, (
        "%d tuile(s) en desaccord X_nat vs X_port sur %d (%s/%s/%s) : %r -- la derniere colonne "
        "est la VENTILATION du port par feuille. Un terme natif NON PORTE d'une AUTRE feuille "
        "produit exactement ce symptome : c'est ainsi que ce cas a ete ouvert"
        % (len(ecarts), len(rows), r33_case.board, r33_case.seed, r33_case.montage, ecarts))


def test_le_mutant_SEPARATEUR_du_montage_est_refute_par_la_mesure(r33_case):
    """LA QUESTION DE CHAQUE MONTAGE : son mutant DOIT diverger du natif.

    Sans cette divergence, `test_le_natif_suit_le_PORT` passerait a vide -- un montage ou les deux
    modeles coincident est un REGIME DEGENERE, pas une preuve."""
    rows = _rows(r33_case)
    div = P.divergences(rows)
    sep = P.MUTANT_SEPARATEUR[r33_case.montage]
    assert div.get(sep, 0) > 0, (
        "le mutant %r rend exactement ce que rend le port sur les %d tuiles mesurees "
        "(divergences par modele : %r) : ce montage ne tranche RIEN" % (sep, len(rows), div))


def test_les_mutants_attendus_mordent_sur_ce_montage(r33_case):
    """CONTRE-EPREUVE : chaque lecture ALTERNATIVE que CE montage separe doit diverger.

    La liste est DERIVEE du montage (`MUTANTS_ATTENDUS`), pas recopiee. Un mutant muet ne condamne
    pas le port -- il dit que ce montage ne le separe pas, et ce decoupage le rend explicite plutot
    que tu. `ABSENT` est l'etat du port AVANT cette tranche : sa divergence CHIFFRE le bug corrige."""
    rows = _rows(r33_case)
    div = P.divergences(rows)
    muets = [nom for nom in MUTANTS_ATTENDUS[r33_case.montage] if not div.get(nom)]
    assert not muets, (
        "mutant(s) qui ne MORDENT PAS sur le montage %r (%s/%s) : %r (divergences mesurees : %r)"
        % (r33_case.montage, r33_case.board, r33_case.seed, muets, div))
    assert not div.get("PORT"), (
        "le modele du port diverge de la mesure : c'est le verdict d'accord qui est rouge, pas la "
        "contre-epreuve (divergences : %r)" % div)


def test_les_inerties_declarees_sont_assertionnees_DANS_LES_DEUX_SENS(r33_case):
    """Une inertie non assertionnee est un trou : un silence s'y lirait comme une confirmation.

    * montages `*-gate` : le carrier ne franchit PAS le gate du corps -> `gate` doit etre FAUX sur
      TOUTES les lignes, et tout mutant qui ne touche pas au gate doit rester muet ;
    * montages normaux : le carrier DOIT franchir le gate sur toutes les lignes, sinon le montage
      ne mesure pas ce qu'il annonce ;
    * `norncrown` : le carrier n'est pas `Synapse`, donc `SANS-SELF` NE PEUT PAS mordre -- et le
      volet self est EXERCE offline (`test_NORNCROWN_gate_DISJONCTIF_rayon_2_et_self_INCLUS`)."""
    rows = _rows(r33_case)
    div = P.divergences(rows)
    if r33_case.montage in P.MONTAGES_GATE_COUPE:
        passe = [r["tile"] for r in rows if r["gate"]]
        assert not passe, (
            "le gate PASSE sur %r alors que le carrier a ete choisi pour qu'il coupe : le montage "
            "ne mesure pas le controle qu'il annonce" % (passe,))
        actifs = [m for m, n in div.items() if n and m not in ("SANS-GATE", "PORT")]
        assert not actifs, (
            "mutant(s) declares INERTES PAR ALGEBRE qui MORDENT : %r (divergences : %r). Quand le "
            "gate coupe, le terme est nul partout et seul `SANS-GATE` peut diverger" % (actifs, div))
    else:
        coupe = [r["tile"] for r in rows if not r["gate"]]
        assert not coupe, (
            "le gate COUPE sur %r alors que le carrier devrait le franchir partout" % (coupe,))
    if r33_case.montage == "norncrown":
        import gameconfig as GC
        from engine.entities.traits.unit_trait import UnitTrait
        traits = (GC.unit(P.NC_CARRIER) or {}).get("traits") or []
        assert UnitTrait.Synapse.name not in traits, (
            "le carrier %s est devenu `Synapse` (%r) : il se satisferait lui-meme sur toutes les "
            "tuiles proches de son origine -- REGIME DEGENERE, il faut changer de carrier"
            % (P.NC_CARRIER, traits))
        assert not div.get("SANS-SELF"), (
            "`SANS-SELF` diverge (%r) alors que le carrier n'est pas Synapse : la mesure et le "
            "modele ne lisent pas le meme substrat" % div.get("SANS-SELF"))
