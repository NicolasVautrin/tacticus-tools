"""#419-r1-tr14-r5-r2 -- la voie ACTIVE de la cascade d'attaque normale.

`IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility` consulte DEUX voies, dans cet
ordre : `GetCustomNormalAttackTypeFromPassive` (`config@+0xa8`, table a 14 entrees, fermee par -r1)
puis, SEULEMENT si elle rend `null`, `GetCustomNormalAttackTypeFromActive` (`config@+0xa0`), dont la
table -- `StaticBattleRules.ActiveAbility` statics `+0x28` -- porte UNE entree :
`1124 PoundThemToDust` -> `1126 RogalDorn_NormalAttack`.

CE QUE CE FICHIER GARDE -- six choses, aucune redondante :

  1. **LA TAILLE DE LA TABLE ACTIVE** (cran OFFLINE). Le `.cctor` empile UN SEUL `Add` entre le
     `ctor` du `Dictionary` et son assignation. Une entree ajoutee sans repasser par la mesure
     doit rougir ici -- et le controle de sur-ensemble du canal (cran 5) devrait etre refait.
  2. **L'ENTREE, contre le natif.** Le port ne croit pas sa propre transcription : une unite a qui
     l'on ECRIT `BC.Units[].ActiveAbilities = [PoundThemToDust]` doit recevoir
     `RogalDorn_NormalAttack` par le seul canal qui publie le resultat de la fabrique --
     `decisionView.units[].abilities` `kind == "normal"`, c.-a-d.
     `ActiveAbilityComponent.NormalAttackType@0x28`.
  3. **LA PRIORITE DE LA CASCADE.** Une unite portant a la fois `PassiveAbilities = [Boltstorm]` ET
     `ActiveAbilities = [PoundThemToDust]` recoit `Boltstorm_NormalAttack` : la voie PASSIVE gagne.
     Ce bras n'est pas decoratif -- la cle active EST montee dans son `ActiveAbilityComponent`
     (mesure : `[1124, 1128]`), donc un port qui repondrait « 1124 present donc 1126 » se
     tromperait exactement la. Avec son TEMOIN (aucune substitution -> `69 Loki_NormalAttack`),
     sans lequel un montage mort rendrait des `69` partout et se lirait comme un succes.
  4. **LE PORT SUR LES CANAUX DE PRODUCTION.** Le foyer n'est pas interroge sur une liste fabriquee
     a la main : il lit `UnitContext.passive_abilities` / `.active_abilities` tels que
     `scene.build_predictor` les seede. Le cran confronte donc la CHAINE ENTIERE -- capteur,
     parsing, seed, foyer -- au champ que la fabrique ecrit.
  5. **LA CONTRE-EPREUVE MORD, ET SEULEMENT LA.** Voie active COUPEE (table videe = le port d'avant
     -r2), le bras `preuve` retombe sur `Loki_NormalAttack` et les TROIS autres ne bougent pas.
     Un vert de (2) sans ce cran ne prouverait pas que c'est la voie active qui le produit ; et
     l'inertie des trois autres est la RECIPROQUE -- un port qui deborderait ferait bouger la borne.
  6. **UNE MACHINE N'A JAMAIS D'ATTAQUE NORMALE.** `MachineFactory$$Build` n'appelle JAMAIS
     `AddNormalAttackAbility` (xrefs : cette fonction a UN SEUL appelant de code,
     `UnitFactory$$Build`). Le cran a DEUX bras, et c'est le second qui porte la preuve : ecrire
     `ActiveAbilities = [PoundThemToDust]` SUR la MoW ne lui donne toujours aucune ability
     `kind == "normal"`. C'est ce qui separe « le port a raison parce que le natif ne monte rien sur
     une Machine » de « le port a raison parce que le kit de CES 8 MoW-la est vide ».

⚠ `PoundThemToDust` n'a AUCUN porteur -- 0 sur les 683 kits gameconfig (5 voies), 0 sur les 175
unites du seed BC. Le montage ECRIT (`catalog_inject.graft_active_ability`, #447) est donc le seul
chemin de confrontation, et c'en est un : ce n'est ni « non pertinent » ni « non confrontable ».

Mesures et RE : `docs/rl/case-419-r1-tr14-r5-r2-voie-active.md`. ASCII only.
Probe jumeau : `scripts/python/probe_419r1tr14r5r2_active_normal_attack.py`.
"""
from __future__ import annotations

import pytest

import probe_419r1tr14r5r2_active_normal_attack as P
from engine.services.custom_normal_attack import CUSTOM_NORMAL_ATTACK_BY_ACTIVE

NATIVE_ACTIVE_TABLE_SIZE = 1     # l'unique `Add` du `.cctor` -- cf. la case-doc


@pytest.fixture(scope="module")
def active_rows(rpc, tmp_path_factory, build_runner):
    """Les quatre bras (preuve / temoin / borne / controle), natif ET port, sur UN runner."""
    P.os.environ["A35_LOGS"] = str(tmp_path_factory.mktemp("tr14r5r2_active"))
    try:
        return P.run_active(rpc, lambda seed, extra: build_runner(seed, extra)["rid"],
                            verbose=False)
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def mow_rows(rpc, tmp_path_factory, build_runner):
    """Les deux bras MoW : telle quelle, puis avec la cle de la voie active ECRITE dessus."""
    P.os.environ["A35_LOGS"] = str(tmp_path_factory.mktemp("tr14r5r2_mow"))
    try:
        return P.run_mow(rpc, lambda seed, extra: build_runner(seed, extra)["rid"], verbose=False)
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)


def _by_role(rows: list, role: str) -> dict:
    hit = [r for r in rows if r.get("role") == role]
    assert len(hit) == 1, f"bras {role!r} attendu une fois, trouve {len(hit)}"
    return hit[0]


def test_table_active_a_la_taille_du_dictionnaire_natif():
    """(1) Cran OFFLINE. Le `.cctor` de `StaticBattleRules.ActiveAbility` empile UN SEUL `Add`
    entre le `ctor` du `Dictionary` et l'assignation a `statics+0x28`."""
    assert len(CUSTOM_NORMAL_ATTACK_BY_ACTIVE) == NATIVE_ACTIVE_TABLE_SIZE, (
        f"la table ACTIVE portee compte {len(CUSTOM_NORMAL_ATTACK_BY_ACTIVE)} entree(s), le "
        f"`.cctor` natif en ecrit {NATIVE_ACTIVE_TABLE_SIZE}. Une entree ajoutee ou retiree doit "
        f"repasser par la mesure -- et le controle de SUR-ENSEMBLE du canal "
        f"(`unitAbilityStates.actives`) doit etre refait pour la nouvelle cle.")
    assert CUSTOM_NORMAL_ATTACK_BY_ACTIVE.get("PoundThemToDust") == "RogalDorn_NormalAttack", (
        "l'unique paire de la table ACTIVE est `1124 PoundThemToDust` -> `1126 "
        "RogalDorn_NormalAttack`, lue au `.cctor` et confrontee live.")


def test_la_voie_active_substitue_l_attaque_normale(active_rows):
    """(2) Bras `preuve` : `ActiveAbilities = [PoundThemToDust]`, aucun passif substituant."""
    r = _by_role(active_rows, "preuve")
    assert r["native"] == "RogalDorn_NormalAttack", (
        f"{r['unit']} avec ActiveAbilities={r['actives']} et PassiveAbilities=[] : le natif rend "
        f"{r['native']!r}, la table ACTIVE annonce `RogalDorn_NormalAttack`.")


def test_la_voie_passive_a_la_priorite_sur_la_voie_active(active_rows):
    """(3) Bras `borne` + son `controle` + le `temoin`. La cascade, pas la seule table."""
    b = _by_role(active_rows, "borne")
    assert b["native"] == "Boltstorm_NormalAttack", (
        f"{b['unit']} porte les DEUX cles (passifs={b['passives']}, actives={b['actives']}) : le "
        f"natif doit rendre celle de la voie PASSIVE, il rend {b['native']!r}. "
        f"`AddNormalAttackAbility` n'atteint la voie active que si la passive rend `null`.")
    c = _by_role(active_rows, "controle")
    assert c["native"] == "Boltstorm_NormalAttack", (
        f"controle apparie : {c['unit']} sans cle active doit rendre la meme valeur que la borne, "
        f"il rend {c['native']!r}.")
    t = _by_role(active_rows, "temoin")
    assert t["native"] == "Loki_NormalAttack", (
        f"TEMOIN : {t['unit']} n'a aucune cle substituante et doit rendre l'attaque normale "
        f"generique, il rend {t['native']!r}. Sans ce cran, un montage MORT rendrait des `69` "
        f"partout et se lirait comme « la voie active ne substitue pas ».")


def test_le_port_reproduit_le_natif_sur_les_quatre_bras(active_rows):
    """(4) `custom_normal_attack` sur les canaux de PRODUCTION, contre le champ natif."""
    bad = [(r["role"], r["unit"], r["native"], r["port"]) for r in active_rows
           if r["port"] != r["native"]]
    assert not bad, (
        "le foyer du port diverge du champ `ActiveAbilityComponent.NormalAttackType@0x28` sur "
        f"{bad} -- format (role, unite, natif, port). Le port lit les MEMES canaux que la "
        "production (`_seed_measured_passives` / `_seed_measured_actives`), donc l'ecart accuse la "
        "chaine entiere : capteur, parsing, seed ou foyer.")


def test_la_contre_epreuve_mord_sur_la_preuve_et_seulement_la(active_rows):
    """(5) Voie active COUPEE = le port d'avant -r2. Doit MORDRE sur `preuve`, rester INERTE
    ailleurs -- l'inertie est la RECIPROQUE, elle borne le fix."""
    bites = {r["role"]: r["cut_bites"] for r in active_rows}
    assert bites.get("preuve") is True, (
        "voie active coupee, le bras `preuve` doit retomber sur `Loki_NormalAttack` : s'il ne bouge "
        "pas, ce n'est PAS la voie active qui produit le vert du cran (2), et le montage ou le "
        "canal est a re-examiner.")
    debords = [role for role, b in bites.items() if role != "preuve" and b]
    assert not debords, (
        f"la contre-epreuve MORD aussi sur {debords}, alors que ces bras ne passent pas par la voie "
        f"active : le port DEBORDE (il laisse la voie active decider la ou la passive doit gagner).")


def test_une_machine_of_war_n_a_jamais_d_attaque_normale(mow_rows):
    """(6) Les deux bras MoW. `MachineFactory$$Build` n'appelle jamais `AddNormalAttackAbility`."""
    assert mow_rows, "montage MoW vide -- aucune Machine sur le board."
    bad = [(r["arm"], r["casterId"], r["normal_abilities"]) for r in mow_rows
           if r["normal_abilities"]]
    assert not bad, (
        f"une Machine publie une ability `kind == \"normal\"` : {bad}. `MachineFactory$$Build` "
        f"appelle `InitBaseComponent`, `MachineFactory$$AddConfiguredAbilities` et "
        f"`UnitFactory$$AddDerivedAbilities` -- jamais `AddNormalAttackAbility`.")
    arms = {r["arm"] for r in mow_rows}
    assert arms == {"ctrl", "active"}, (
        f"les DEUX bras sont requis, trouve {sorted(arms)} : sans le bras `active` (cle de la voie "
        f"active ECRITE sur la MoW), le vert ne distinguerait pas « le natif ne monte rien sur une "
        f"Machine » de « le kit de ces MoW-la est vide ».")
