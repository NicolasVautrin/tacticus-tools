"""#419-r1-tr14-r5-r2-r2 -- la garde `FilterNewList` du REPLI GENERIQUE de l'attaque normale.

Dernier etage de `IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility`, apres PASSIVE
(-r1), ACTIVE (-r2) et TRAIT (-r2-r1). Le `else` final, lu verbatim :

    var list = ListExtensions.FilterNewList(comp@+0x20, a => IsRegularAttack(a@+0x44));
    if (0 < list.Count) return;                  // rien n'est ajoute
    type = this@+0x20;                           // le generique

La garde est NON VIDE parce que `UnitFactory$$Build` appelle `AddConfiguredAbilities` AVANT
`AddNormalAttackAbility`, et que `UnitFactory$$AddActiveAbility` y monte INCONDITIONNELLEMENT
chaque `BC.Units[].ActiveAbilities` dans ce meme composant.

CE QUE CE FICHIER GARDE -- cinq choses, aucune redondante :

  1. **LA GARDE, contre le natif.** Une unite a qui l'on ECRIT une attaque REGULIERE dans
     `BC.Units[].ActiveAbilities` ne recoit PAS la generique par-dessus : son
     `ActiveAbilityComponent.NormalAttackType@0x28` reste celle qu'elle porte deja. C'est la ligne
     `preuve`, et c'est la SEULE qui separe les deux modeles -- un moteur sans la garde y repond
     `Loki_NormalAttack`.
  2. **LES DEUX TEMOINS.** `temoin-nonreg` (une active NON reguliere, greffee par le meme chemin)
     et `temoin-origine` (les actives d'origine) doivent recevoir la generique. Ils BORNENT : une
     garde qui mordrait trop large priverait toute unite de son attaque normale, et c'est la
     regression que `temoin-nonreg` est la pour attraper -- il isole la NATURE de l'active, pas le
     fait qu'on ait greffe.
  3. **LE RANG -- QUATRIEME.** `ordre-pas` porte l'active reguliere ET `PassiveAbilities =
     [Boltstorm]` : la voie PASSIVE (rang 1) doit gagner et rendre `Boltstorm_NormalAttack`. La
     garde vit dans le `else` du `else` du `else` ; portee trop haut elle rendrait
     `TemplarInitiateNormalAttack` et ferait rougir cette ligne.
  4. **LE PORT SUR LES CANAUX DE PRODUCTION.** Le foyer n'est pas interroge sur une liste fabriquee
     a la main : il lit `UnitContext.active_abilities` / `.passive_abilities` / `.traits` tels que
     `scene.build_predictor` les seede. Le cran confronte donc la CHAINE ENTIERE au champ que la
     fabrique ecrit.
  5. **LE FOYER PORTE EST JUSTE, ET L'ECART RESIDUEL EST BORNE.** `normal_attack_already_present`
     s'accorde au natif sur les quatre bras -- donc ce qui reste ouvert est un probleme de CANAL,
     pas de RE. Et l'ecart de port subsistant est fige a la seule ligne `preuve` : le cliquet
     rougit s'il s'elargit comme s'il se ferme.

⚠ **La garde est PORTEE mais NON BRANCHEE dans `custom_normal_attack`, et c'est un arbitrage
MESURE** : elle exige `config.ActiveAbilities` (l'etat AVANT la fabrique), le canal ne donne que
l'etat APRES. Branchee dessus, elle repondrait juste meme voie amont coupee -- elle rend alors
INERTE la contre-epreuve de la voie ACTIVE (#565), mesure -- et elle n'apporterait rien en
production (**0 des 175 unites du seed** n'a d'attaque reguliere dans `BC.Units[].ActiveAbilities`).
Residu `#419-r1-tr14-r5-r2-r2-r1`.

⚠ **Le canal est un SUR-ENSEMBLE, et c'est MESURE ici** (`test_le_canal_est_un_sur_ensemble`) :
`UnitContext.active_abilities` lit l'`ActiveAbilityComponent` APRES la fabrique, donc il porte
AUSSI l'attaque normale qu'elle vient d'y ecrire. C'est ce qui rend la lecture « DERNIERE
reguliere » correcte des deux cotes de la garde -- et ce cran est ce qui empeche de la croire
equivalente a `BC.Units[].ActiveAbilities`.

⚠ Aucune des 18 attaques regulieres n'a de config d'ability derivable (0/18 au gameconfig, 0/131
dans `BC.Abilities.ActiveAbilities` du seed) : le montage ECRIT l'id directement, et
`catalog_inject.graft_active_ability` est inutilisable ici (il synthetiserait une config).

Mesures et RE : `docs/rl/case-419-r1-tr14-r5-r2-r2-garde-filternewlist.md`. ASCII only.
Probe jumeau : `scripts/python/probe_419r1tr14r5r2r2_filter_new_list.py`.
"""
from __future__ import annotations

import pytest

import probe_419r1tr14r5r2r2_filter_new_list as P
from engine.services.custom_normal_attack import normal_attack_already_present


@pytest.fixture(scope="module")
def guard_rows(rpc, tmp_path_factory, build_runner):
    """Les quatre unites d'un unique build, natif ET port."""
    P.os.environ["A35_LOGS"] = str(tmp_path_factory.mktemp("tr14r5r2r2_guard"))
    try:
        return P.run(rpc, lambda seed, extra: build_runner(seed, extra)["rid"], verbose=False)
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)


def _row(rows: list, role: str) -> dict:
    hit = [r for r in rows if r.get("role") == role]
    assert len(hit) == 1, f"role {role!r} attendu une fois, trouve {len(hit)}"
    return hit[0]


def test_le_foyer_rend_la_derniere_reguliere_offline():
    """Cran OFFLINE du foyer : c'est la DERNIERE qui gagne (mirror de `comp@+0x28`, que
    `ActiveAbilityComponent$$Add` reecrit a chaque reguliere), et un canal muet ne deduit rien."""
    assert normal_attack_already_present(None) is None, (
        "canal muet (`None`) : le foyer ne doit RIEN deduire -- c'est le tri-etat des voies "
        "voisines, et le repli generique doit rester celui d'avant.")
    assert normal_attack_already_present([]) is None, (
        "collection MESUREE et vide : aucune reguliere -> le repli generique s'applique.")
    assert normal_attack_already_present(["FireAndReposition"]) is None, (
        "une active NON reguliere ne fait pas mordre la garde : `IsRegularAttack` est un "
        "`Contains` sur les 18, pas « l'unite a une active ».")
    assert normal_attack_already_present(
        ["TemplarInitiateNormalAttack", "Boltstorm_NormalAttack"]) == "Boltstorm_NormalAttack", (
        "deux regulieres : c'est la DERNIERE qui s'impose. Contraste VOULU avec les deux voies de "
        "table, ou le PREMIER gagnant s'impose -- ici le natif ne choisit pas, c'est "
        "`ActiveAbilityComponent$$Add` qui reecrit `comp@+0x28` a chaque reguliere ajoutee.")
    assert normal_attack_already_present(["__pas_un_membre_d_enum__"]) is None, (
        "un nom hors enum du build n'est ni ingerable ni devinable : il est saute, pas devine.")


def test_la_garde_empeche_le_repli_generique(guard_rows):
    """(1) `preuve` : une attaque REGULIERE ecrite dans `BC.Units[].ActiveAbilities`."""
    r = _row(guard_rows, "preuve")
    assert r["native"] == P.REGULAR_GRAFT, (
        f"{r['unit']} porte `ActiveAbilities=[{P.REGULAR_GRAFT}]` (une attaque REGULIERE), "
        f"PassiveAbilities=[] et aucun trait `Boss` : les trois voies rendent `null`, la fabrique "
        f"atteint le repli, y trouve une reguliere deja montee et REND SANS RIEN AJOUTER. Le natif "
        f"rend {r['native']!r}.")


def test_les_temoins_recoivent_bien_la_generique(guard_rows):
    """(2) La garde ne mord pas sur une active ordinaire -- deux temoins, dont un GREFFE."""
    for role in ("temoin-nonreg", "temoin-origine"):
        t = _row(guard_rows, role)
        assert t["native"] == P.GENERIC, (
            f"[{role}] {t['unit']} n'a AUCUNE attaque reguliere montee : la collection filtree est "
            f"vide, le repli generique s'applique et le natif doit rendre {P.GENERIC!r}, il rend "
            f"{t['native']!r}.")
        assert t["port"] == P.GENERIC, (
            f"[{role}] le port rend {t['port']!r} : une garde qui mord ici priverait toute unite "
            f"ordinaire de son attaque normale. `temoin-nonreg` est GREFFE par le meme chemin que "
            f"`preuve` -- c'est la NATURE de l'active qui doit decider, pas la greffe.")


def test_la_garde_est_le_quatrieme_etage_de_la_cascade(guard_rows):
    """(3) `ordre-pas` : une voie de rang SUPERIEUR gagne malgre la reguliere montee."""
    r = _row(guard_rows, "ordre-pas")
    assert r["native"] == P.PASSIVE_VALUE, (
        f"{r['unit']} porte `ActiveAbilities=[{P.REGULAR_GRAFT}]` ET "
        f"`PassiveAbilities=[{P.PASSIVE_KEY}]` : la voie PASSIVE est consultee la PREMIERE et "
        f"gagne, donc le natif rend {P.PASSIVE_VALUE!r} -- il rend {r['native']!r}.")
    assert r["port"] == P.PASSIVE_VALUE, (
        f"le port rend {r['port']!r} : la garde a ete portee TROP HAUT dans la cascade. Elle est "
        f"le `else` du `else` du `else` -- elle ne doit jamais decider quand une voie a gagne.")


def test_le_canal_actives_est_un_sur_ensemble(guard_rows):
    """(4) Ce qui rend la lecture du port valide -- et qu'on ne peut pas SUPPOSER.

    `UnitContext.active_abilities` lit l'`ActiveAbilityComponent` APRES la fabrique. Sur un temoin,
    le generique que la fabrique vient de poser DOIT donc y figurer. Si ce cran devenait faux, le
    canal serait devenu `BC.Units[].ActiveAbilities` et la lecture « derniere reguliere » n'aurait
    plus le meme sens des deux cotes de la garde."""
    t = _row(guard_rows, "temoin-origine")
    assert P.GENERIC in t["canal_actives"], (
        f"le canal mesure {t['canal_actives']} pour {t['unit']} : le generique {P.GENERIC!r} que la "
        f"fabrique vient de poser devrait y etre. Le canal n'est donc plus le SUR-ENSEMBLE "
        f"documente, et la borne du foyer est a re-examiner.")
    p = _row(guard_rows, "preuve")
    assert P.GENERIC not in p["canal_actives"], (
        f"bras `preuve` : le canal mesure {p['canal_actives']}, or la garde a MORDU -- la fabrique "
        f"n'a rien ajoute, donc {P.GENERIC!r} ne doit PAS y figurer. Sa presence signifierait que "
        f"le natif a bien pose la generique, c.-a-d. qu'il n'y a pas de garde.")
    for r in guard_rows:
        assert r["canal_regulars"], (
            f"[{r['role']}] {r['unit']} : le canal ne porte AUCUNE attaque reguliere "
            f"({r['canal_actives']}), alors que toute unite en recoit une. Canal muet ou tronque -- "
            f"le port lirait alors `None` et repondrait generique par defaut.")
        assert r["canal_regulars"][-1] == r["native"], (
            f"[{r['role']}] la DERNIERE reguliere du canal ({r['canal_regulars'][-1]!r}) doit etre "
            f"le `NormalAttackType` natif ({r['native']!r}). C'est l'invariant sur lequel le foyer "
            f"repose : `ActiveAbilityComponent$$Add` reecrit `comp@+0x28` a chaque reguliere.")


def test_le_foyer_porte_s_accorde_au_natif_sur_les_quatre_bras(guard_rows):
    """(5) Le foyer EST juste -- mesure, alors meme qu'il n'est pas branche.

    `normal_attack_already_present` est un mirror de la garde, mais `custom_normal_attack` ne
    l'appelle pas (cf. sa docstring : le substrat exact, `config.ActiveAbilities`, n'est pas
    disponible). Ce cran etablit qu'il rend la BONNE valeur sur les quatre bras -- c'est ce qui
    rend le residu `-r2-r2-r1` purement un probleme de CANAL, pas de RE."""
    bad = [(r["role"], r["foyer"], r["native"]) for r in guard_rows if r["foyer"] != r["native"]]
    assert not bad, (
        f"le foyer de la garde diverge du `NormalAttackType` natif sur {bad} -- format (role, "
        f"foyer, natif). Il lit pourtant le canal MESURE : l'ecart accuse la RE de la garde "
        f"elle-meme, pas le canal.")


def test_l_ecart_de_port_residuel_est_celui_documente(guard_rows):
    """(6) CLIQUET DE RESIDU (`#419-r1-tr14-r5-r2-r2-r1`).

    La garde n'etant pas branchee, le port repond encore `Loki_NormalAttack` sur `preuve` -- et
    SEULEMENT la. Ce cran fige cet ecart CONNU : il rougit s'il s'AGGRAVE (une autre ligne se met
    a diverger) comme s'il se FERME (la garde a ete branchee, et alors c'est cette case-doc et ce
    fichier qu'il faut mettre a jour, pas le test qu'il faut faire taire)."""
    gaps = sorted(r["role"] for r in guard_rows if r["port_gap"])
    assert gaps == ["preuve"], (
        f"l'ecart de port residuel porte sur {gaps}, attendu exactement ['preuve']. S'il s'est "
        f"FERME, la garde a ete branchee : mettre a jour "
        f"`docs/rl/case-419-r1-tr14-r5-r2-r2-garde-filternewlist.md` et ce cran. S'il s'est "
        f"ELARGI, le port a regresse sur une ligne que la garde ne concerne pas.")
    p = _row(guard_rows, "preuve")
    assert p["port"] == P.GENERIC, (
        f"sur `preuve`, le port repond {p['port']!r} ; l'ecart documente est qu'il repond "
        f"{P.GENERIC!r} (le repli generique s'applique faute de garde branchee).")
