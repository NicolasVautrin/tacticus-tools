/* EXTRACTEUR DU PLAN DE RAIDS -- tacticusplanner.app/plan/dailyRaids
 *
 * A jouer par `mcp__chrome-devtools__evaluate_script` sur la page ouverte et CONNECTEE, avec
 * `filePath: logs/planner-raids.json`. Puis :
 *
 *     python scripts/python/raids_plan.py
 *
 * (!)IL Y A PLUSIEURS ONGLETS, ET N'EN LIRE QU'UN PERD DES LIGNES EN SILENCE. Mesure du
 * 2026-08-27 : `Locator Beacon` etait absent de l'export alors qu'il est bel et bien planifie --
 * il vit dans l'onglet << extra energy >>. Le DOM ne porte QUE l'onglet actif, donc un scrape
 * en une passe rend un fichier d'apparence saine, avec un en-tete COMPLET (`energieTotale` est
 * un texte toujours present) pose sur des lignes PARTIELLES. C'est la combinaison la plus
 * trompeuse : le total valide la liste qu'il contredit. On parcourt donc TOUS les onglets, et
 * on RESTAURE celui qui etait actif en partant.
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
async () => {
    // --- signature du contenu : ce qui change quand un onglet se rend ---------------------------
    const signature = () =>
        document.querySelectorAll('img[src*="ui_icon_upgrade_"]').length + "|" +
        document.body.innerText.length;

    /* ⚠ ON ATTEND UN SIGNAL, PAS UNE DUREE. Un `setTimeout(400)` marche jusqu'au jour ou la page
     * est lente, et il echoue alors SANS LE DIRE -- on rescrapperait l'onglet precedent en
     * croyant lire le nouveau. On attend donc que la signature du DOM se STABILISE (identique
     * sur 3 frames d'affilee), avec une borne de securite qui, si elle est atteinte, est
     * RAPPORTEE (`stabilise: false`) au lieu d'etre avalee. */
    const attendreStable = async (borneFrames = 240) => {
        let prec = null, stables = 0;
        for (let i = 0; i < borneFrames; i++) {
            await new Promise((r) => requestAnimationFrame(r));
            const s = signature();
            stables = s === prec ? stables + 1 : 0;
            prec = s;
            if (stables >= 3) return true;
        }
        return false;
    };

    // --- une passe de scrape sur l'onglet COURANT ----------------------------------------------
    const scraper = () => {
        const out = { materiaux: [], desaccords: [] };
        const brut = document.body.innerText;
        const L = brut.split("\n").map((s) => s.trim());

        // 1. compteurs, par le texte a plat : "<couvert>/<requis>" puis le nom
        //
        // (!)LE PREMIER NOMBRE N'EST PAS L'INVENTAIRE -- C'EST `min(inventaire, requis)`.
        // Il dit ce qui est COUVERT du besoin, PLAFONNE au besoin. Mesure du 2026-08-22 sur les
        // 24 lignes du plan : sur les 22 ou `couvert < requis`, il vaut EXACTEMENT la quantite
        // lue en jeu (22/22) ; les 2 seules divergences apparentes etaient les 2 lignes ou
        // `couvert == requis` -- Kill Count << 4/4 >> pour 7 en stock, Boon of Slaanesh << 0/0 >>
        // pour 6. Le plafond, pas un retard de synchronisation.
        //
        // ⛔ NE PAS le renommer `possede` : c'est ce nom-la qui a fait lire un plafond comme un
        // inventaire, et conclure a tort que le planner datait et reclamait un << Sync with
        // Tacticus >>. Une ligne plafonnee ne dit RIEN de l'avoir -- seulement qu'il suffit.
        const cpt = /^(\d+)\/(\d+)$/;
        const parTexte = [];
        for (let i = 0; i + 1 < L.length; i++) {
            const m = L[i].match(cpt);
            if (!m) continue;
            const nom = L[i + 1];
            if (!nom || cpt.test(nom) || /^\d+$/.test(nom)) continue;
            parTexte.push({ nom, couvert: +m[1], requis: +m[2] });
        }

        // 1bis. L'ID DE MATERIAU, LU DANS L'URL DE SON ICONE
        //
        // (!)C'EST LUI QUI FERME LA BOUCLE AVEC LE JEU. Le planner n'affiche que des noms
        // anglais (<< Pile of Salvage >>) ; l'inventaire vivant, lui, est indexe par identifiant
        // (`upgArmC003`). Sans cet id il faudrait une table nom -> id ecrite a la main, qui se
        // perimerait au premier materiau ajoute. L'icone porte l'id dans son nom de fichier :
        // `ui_icon_upgrade_upgArmC003-BeDLXVw0.png`, et son `alt` porte le nom -- les deux bouts
        // du pont sont dans le meme element.
        const idParNom = {};
        document.querySelectorAll('img[src*="ui_icon_upgrade_"]').forEach((im) => {
            const m = (im.getAttribute("src") || "").match(/ui_icon_upgrade_([A-Za-z0-9]+)-/);
            if (m && im.alt) idParNom[im.alt.trim()] = m[1];
        });

        // 2. noeuds, par parcours DOM en ordre de document
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

        // 3. jointure, et le desaccord se DIT
        const n = Math.max(parTexte.length, parDom.length);
        for (let i = 0; i < n; i++) {
            const a = parTexte[i], b = parDom[i];
            if (!a || !b) {
                out.desaccords.push({ index: i, texte: a || null, dom: b || null });
                continue;
            }
            if (a.nom !== b.nom) out.desaccords.push({ index: i, texte: a.nom, dom: b.nom });
            // `id` a `null` = NON APPARIE, jamais devine : l'appelant le verra et pourra le dire.
            out.materiaux.push({ nom: a.nom, id: idParNom[a.nom] ?? null,
                                 couvert: a.couvert, requis: a.requis, noeuds: b.noeuds });
        }
        return out;
    };

    const res = { entete: {}, materiaux: [], desaccords: [] };

    // --- l'EN-TETE : il vit hors des onglets, on le lit une fois -------------------------------
    const brut0 = document.body.innerText;
    const L0 = brut0.split("\n").map((s) => s.trim());
    const mPlan = brut0.match(/Raids plan \(\s*(\d+)\s*Days\s*\|\s*\n?\s*(\d+)/);
    if (mPlan) { res.entete.jours = +mPlan[1]; res.entete.energieTotale = +mPlan[2]; }
    const mToday = brut0.match(/Today \(\s*(\d+)[^|]*\|\s*(\d+)\s*raids/);
    if (mToday) { res.entete.energieDuJour = +mToday[1]; res.entete.raidsDuJour = +mToday[2]; }
    const iDate = L0.findIndex((s) => /^\d+(st|nd|rd|th) of \w+$/.test(s));
    if (iDate >= 0) res.entete.finPrevue = L0[iDate];

    // --- LA MARCHE PAR ONGLETS ------------------------------------------------------------------
    const onglets = Array.from(document.querySelectorAll('[role="tab"]'));
    const actifAuDepart = onglets.findIndex((t) => t.getAttribute("aria-selected") === "true");
    // ⚠ Tri-etat : `null` = AUCUN onglet trouve (page a une seule vue, ou selecteur perime),
    //   ce qui n'est PAS la meme chose qu'une liste vide. L'appelant doit pouvoir distinguer
    //   << il n'y avait qu'une vue >> de << je n'ai pas su les trouver >>.
    res.entete.onglets = onglets.length ? [] : null;

    const vus = new Set();
    const absorber = (part, etiquette) => {
        for (const m of part.materiaux) {
            // Un materiau peut apparaitre dans deux onglets : on garde la PREMIERE occurrence
            // et on note d'ou elle vient, plutot que d'ecraser avec des `requis` d'une autre vue.
            if (vus.has(m.nom)) continue;
            vus.add(m.nom);
            res.materiaux.push({ ...m, onglet: etiquette });
        }
        for (const d of part.desaccords) res.desaccords.push({ ...d, onglet: etiquette });
    };

    if (!onglets.length) {
        absorber(scraper(), null);
    } else {
        for (let i = 0; i < onglets.length; i++) {
            const t = onglets[i];
            const etiquette = (t.innerText || "").trim().replace(/\s+/g, " ") || ("onglet " + i);
            let stabilise = true;
            if (t.getAttribute("aria-selected") !== "true") {
                t.click();
                stabilise = await attendreStable();
            }
            const avant = res.materiaux.length;
            absorber(scraper(), etiquette);
            res.entete.onglets.push({
                nom: etiquette, lignesNeuves: res.materiaux.length - avant, stabilise,
            });
        }
        // On RESTAURE l'onglet de depart : l'extraction ne doit pas laisser la page ailleurs
        // qu'ou l'utilisateur l'avait mise.
        if (actifAuDepart >= 0 &&
            onglets[actifAuDepart].getAttribute("aria-selected") !== "true") {
            onglets[actifAuDepart].click();
            await attendreStable();
        }
    }
    return res;
}
