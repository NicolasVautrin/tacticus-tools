"""#462-r4b-r1-r1-r1-r1-b-r1-r1-r1 -- CONFRONTATION LIVE du 4e conjoint de
`MasterOfTheTutelaries_SummonAbility$$CreateTrigger` sur une cible `Object`.

CE QUE CE FICHIER VERROUILLE, ET POURQUOI IL EXISTE. Le recensement gameconfig dit : les 28
porteurs du trait `Object` (13) sont TOUS des `LootObj_*` npc, aucun n'est dans
`data/seed-bc.json`, aucun n'entre dans `rl_duel build --list-pool`. On pouvait en conclure
<< regime inatteignable, correctif cosmetique >>. **C'est faux.** Un `LootObj_*` s'amene en
bataille par un montage ECRIT (cf. `jouer_bras` du probe) :

  1. `catalog_inject.write_augmented_seed_bc` l'ajoute au bloc `Units` du seed ;
  2. on lui force `Health` -- `buildNormalizedBC` ne le NORMALISE pas (pas de progression, d'ou
     son absence du pool) mais GARDE son entree dans le template ;
  3. on le pose a la tuile voulue via `initAndStart.playerUnits` + `playerId = PLAYER_ID_AI`
     (voie `--a-place`, #477-r5), ce qui contourne le refus de pool.

LE CRITERE, en DEUX BRAS APPARIES. Meme roster, meme tuile de cast, meme seed, meme board : seule
change l'unite AU CONTACT du Pink Horror invoque par 1096 -- donc la cible de son attaque Psychic
d'apparition. L'autre ennemi est exile au coin oppose, sinon le Horror pourrait le choisir et le
bras ne discriminerait plus rien.

  bras `crate`  -> cible `LootObj_Crate_Imp` (Object 13)   : le natif produit **0** Screamer
  bras `warden` -> cible `necroWarden` (vraie unite)        : le natif produit **1** Screamer

Et sur ce MEME etat live, le port d'AVANT ce fix (recopie `{Steppable, Decoy}` rejouee par
substitution) rend `matches(crate) = True` : il aurait spawne un Screamer que le natif ne produit
pas. L'ecart est donc CONFRONTE, pas seulement lu au decompile.

NON-VACUITE. Le bras `crate` rend zero ; un zero est le resultat le plus facile a obtenir pour de
mauvaises raisons. Deux gardes le rendent attribuable, et elles sont assertionnees AVANT lui :
le Pink Horror doit etre APPARU, et la cible doit avoir PERDU des PV (l'attaque a bien eu lieu).

COUT : 2 runners (un par bras), disposes par le probe. Le pendant OFFLINE
(`test_master_tutelaries_object_or_steppable_offline.py`) garde le meme conjoint sans runner.

ASCII only (cp1252).
"""
from __future__ import annotations

import pytest

import probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r1_mot_object_or_steppable as P


@pytest.fixture(scope="module")
def bras_apparies(live_session):
    """Joue les DEUX bras. Un montage qui ne s'installe pas ECHOUE (#268) : un skip ici serait un
    vert qui ment -- aucune mesure n'aurait eu lieu et rien ne rougirait pour personne."""
    out = {}
    for bras in ("crate", "warden"):
        try:
            out[bras] = P.jouer_bras(live_session, bras)
        except Exception as e:                                        # noqa: BLE001
            pytest.fail("montage du bras %r REFUSE (%s): %s -- le board/le seed ne portent pas "
                        "ce montage ; ce n'est ni un verdict natif ni un verdict de port."
                        % (bras, type(e).__name__, e))
    return out


def test_premisse_le_crate_arrive_ennemi_et_porte_le_trait_object(bras_apparies):
    """PREMISSE 1 -- les deux conjoints AMONT du conjoint teste sont satisfaits sur le crate.

    `AreEnemies(owner@+0x30, target@+0x60)` : le crate arrive sur une team DIFFERENTE de celle
    d'Abraxas. Et le substrat de traits du port lit bien `Object` sur lui (sans quoi le conjoint
    ne pourrait pas mordre pour une raison qui n'aurait rien a voir avec sa fidelite)."""
    c = bras_apparies["crate"]
    assert c["team_cible"] is not None and c["team_abraxas"] is not None
    assert c["team_cible"] != c["team_abraxas"], (
        "le crate est arrive sur la MEME team qu'Abraxas (%s) -- `AreEnemies` est faux, donc le "
        "4e conjoint n'est jamais atteint et ce fichier ne mesure rien."
        % (c["team_cible"],))
    assert "Object" in c["traits_vus"], (
        "le substrat du port ne voit pas `Object` sur le crate (traits vus : %r)."
        % (c["traits_vus"],))
    assert "Steppable" not in c["traits_vus"], (
        "le crate porte AUSSI `Steppable` (%r) : il serait gate par l'ancienne recopie aussi, "
        "donc ce bras ne discriminerait rien." % (c["traits_vus"],))


@pytest.mark.parametrize("bras", ["crate", "warden"])
def test_premisse_le_horror_est_apparu_et_a_attaque(bras_apparies, bras):
    """PREMISSE 2 -- la NON-VACUITE du zero. A lire AVANT le compte de Screamers : un bras ou le
    Horror n'apparait pas, ou n'attaque pas, rendrait 0 Screamer pour une raison qui n'a rien a
    voir avec le conjoint."""
    r = bras_apparies[bras]
    assert r["d_horror"] >= 1, "bras %s : aucun Pink Horror invoque par 1096" % bras
    assert r["hp_avant"] is not None and r["hp_apres"] is not None, \
        "bras %s : PV de la cible non lus (%r -> %r)" % (bras, r["hp_avant"], r["hp_apres"])
    assert r["hp_apres"] < r["hp_avant"], (
        "bras %s : la cible n'a PAS ete attaquee (%s -> %s) -- le compte de Screamers ne mesure "
        "alors rien." % (bras, r["hp_avant"], r["hp_apres"]))


def test_le_natif_arme_bien_la_chaine_sur_une_vraie_unite(bras_apparies):
    """CONTROLE -- sur une vraie unite, la chaine 1173 fire. Sans ce fait, le zero du bras
    `crate` ne serait qu'une chaine desarmee."""
    assert bras_apparies["warden"]["d_screamer"] >= 1, (
        "0 Screamer sur `necroWarden` : la chaine 1173 n'est pas armee dans ce montage, donc le "
        "bras `crate` ne mesure rien.")


def test_le_natif_refuse_le_screamer_sur_une_cible_object(bras_apparies):
    """LE CRITERE NATIF. `NOT IsObjectOrSteppable(sel@+0x60)` : le natif n'invoque AUCUN Screamer
    quand la cible de l'attaque Psychic porte le trait `Object` (13)."""
    c = bras_apparies["crate"]
    assert c["d_screamer"] == 0, (
        "le natif a produit %d Screamer(s) sur une cible `Object` -- la lecture du conjoint 4 "
        "serait fausse." % c["d_screamer"])


def test_le_port_accorde_avec_le_natif_sur_les_deux_bras(bras_apparies):
    """L'AGREMENT. `matches` du port, evalue sur l'ETAT LIVE de chaque bras, rend le meme verdict
    que le natif : refus sur le crate, acceptation sur la vraie unite."""
    c, w = bras_apparies["crate"], bras_apparies["warden"]
    assert c["port"] is False, (
        "le port ACCEPTE une cible `Object` (traits vus %r) alors que le natif a produit 0 "
        "Screamer -- il spawnerait un Screamer que le natif ne produit pas." % (c["traits_vus"],))
    assert w["port"] is True, (
        "le port REFUSE une vraie unite alors que le natif a produit %d Screamer(s) -- le "
        "conjoint mord trop large." % w["d_screamer"])


def test_contre_epreuve_la_recopie_infidele_desaccorde_sur_le_crate(bras_apparies):
    """CONTRE-EPREUVE -- c'est elle qui prouve que ce fichier mesure le FIX, pas un acquis.

    On rejoue le port d'AVANT (`{Steppable, Decoy}`) sur le MEME etat live : il rend `True` sur le
    crate, la ou le natif a rendu 0 Screamer. Le desaccord est donc REEL et il etait LA.

    ⚠ On verifie d'abord que la substitution A MORDU : une mutation jamais consultee rendrait
    << verdict identique >>, qu'un lecteur presse lirait comme << le fix ne change rien >>."""
    c = bras_apparies["crate"]
    assert c["recopie_consultee"] > 0, (
        "MUTATION INERTE : la recopie substituee n'a ete consultee que %r fois -- la "
        "contre-epreuve ne mesure RIEN." % (c["recopie_consultee"],))
    assert c["port_recopie"] is True, (
        "la recopie `{Steppable, Decoy}` rejouee rend %s sur le crate : elle ne reconstitue pas "
        "le port d'AVANT, donc l'ecart mesure ici n'est pas celui que le fix ferme."
        % c["port_recopie"])
    assert c["port_recopie"] != c["port"], (
        "le port courant et la recopie rendent le MEME verdict sur le crate -- le fix serait un "
        "no-op.")
