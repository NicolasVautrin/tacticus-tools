/* EXTRACTEUR DU PLAN DE RAIDS -- tacticusplanner.app/plan/dailyRaids
 *
 * A jouer par `mcp__chrome-devtools__evaluate_script` sur la page ouverte et CONNECTEE, avec
 * `filePath: logs/planner-raids.json`. Puis :
 *
 *     python scripts/python/raids_plan.py
 *
 * (!)LE NOM COMPLET DE LA CAMPAGNE VIENT DE `aria-label`, PAS DE L'ABREVIATION AFFICHEE.
 * Les libelles visibles (`Ind`, `SHME`, `FoCE`...) sont une invention du planner : aucune regle
 * ne les derive du nom (`Indomitus` -> `Ind` mais `Octarius` -> `O` et `Fall of Cadia` -> `FoC`),
 * donc les traduire exigerait une table ECRITE A LA MAIN, qui se perimerait a la premiere
 * campagne ajoutee. Le bouton, lui, porte `aria-label="Saim-Hann Mirror Elite"` -- exactement le
 * nom que la localisation du JEU associe a `eliteMirror4`. On lit celui-la.
 *
 * (!)DEUX LECTURES CROISEES, ET C'EST VOULU. Les compteurs viennent du TEXTE A PLAT (motif
 * `x/y` sur une seule ligne, suivi du nom) ; les noeuds viennent d'un PARCOURS DOM en ordre de
 * document. Les deux listes doivent avoir la meme longueur et les memes noms dans le meme ordre
 * -- `desaccords` le dit. Un seul des deux chemins qui derive silencieusement serait invisible.
 */
() => {
    const res = { entete: {}, materiaux: [], desaccords: [] };
    const brut = document.body.innerText;
    const L = brut.split("\n").map((s) => s.trim());

    const mPlan = brut.match(/Raids plan \(\s*(\d+)\s*Days\s*\|\s*\n?\s*(\d+)/);
    if (mPlan) { res.entete.jours = +mPlan[1]; res.entete.energieTotale = +mPlan[2]; }
    const mToday = brut.match(/Today \(\s*(\d+)[^|]*\|\s*(\d+)\s*raids/);
    if (mToday) { res.entete.energieDuJour = +mToday[1]; res.entete.raidsDuJour = +mToday[2]; }
    const iDate = L.findIndex((s) => /^\d+(st|nd|rd|th) of \w+$/.test(s));
    if (iDate >= 0) res.entete.finPrevue = L[iDate];

    // --- 1. compteurs, par le texte a plat : "<possede>/<requis>" puis le nom -----------------
    const cpt = /^(\d+)\/(\d+)$/;
    const parTexte = [];
    for (let i = 0; i + 1 < L.length; i++) {
        const m = L[i].match(cpt);
        if (!m) continue;
        const nom = L[i + 1];
        if (!nom || cpt.test(nom) || /^\d+$/.test(nom)) continue;
        parTexte.push({ nom, possede: +m[1], requis: +m[2] });
    }

    // --- 1bis. L'ID DE MATERIAU, LU DANS L'URL DE SON ICONE ------------------------------------
    //
    // (!)C'EST LUI QUI FERME LA BOUCLE AVEC LE JEU. Le planner n'affiche que des noms anglais
    // (<< Pile of Salvage >>) ; l'inventaire vivant, lui, est indexe par identifiant
    // (`upgArmC003`). Sans cet id il faudrait une table nom -> id ecrite a la main, qui se
    // perimerait au premier materiau ajoute. L'icone porte l'id dans son nom de fichier :
    // `ui_icon_upgrade_upgArmC003-BeDLXVw0.png`, et son `alt` porte le nom -- les deux bouts du
    // pont sont dans le meme element.
    const idParNom = {};
    document.querySelectorAll('img[src*="ui_icon_upgrade_"]').forEach((im) => {
        const m = (im.getAttribute("src") || "").match(/ui_icon_upgrade_([A-Za-z0-9]+)-/);
        if (m && im.alt) idParNom[im.alt.trim()] = m[1];
    });

    // --- 2. noeuds, par parcours DOM en ordre de document -------------------------------------
    const parDom = [];
    let courant = null;
    document.querySelectorAll("h4, button").forEach((el) => {
        if (el.tagName === "H4") {
            courant = { nom: el.innerText.trim(), noeuds: [] };
            parDom.push(courant);
            return;
        }
        const t = (el.innerText || "").trim().replace(/\s+/g, " ");
        const m = t.match(/^([A-Za-z]+) (\d+)$/);
        if (!m || !courant) return;
        const complet = el.getAttribute("aria-label");
        courant.noeuds.push({ campagne: complet, abrege: m[1], noeud: +m[2] });
    });

    // --- 3. jointure, et le desaccord se DIT ---------------------------------------------------
    const n = Math.max(parTexte.length, parDom.length);
    for (let i = 0; i < n; i++) {
        const a = parTexte[i], b = parDom[i];
        if (!a || !b) { res.desaccords.push({ index: i, texte: a || null, dom: b || null }); continue; }
        if (a.nom !== b.nom) res.desaccords.push({ index: i, texte: a.nom, dom: b.nom });
        // `id` a `null` = NON APPARIE, jamais devine : l'appelant le verra et pourra le dire.
        res.materiaux.push({ nom: a.nom, id: idParNom[a.nom] ?? null,
                             possede: a.possede, requis: a.requis, noeuds: b.noeuds });
    }
    return res;
}
