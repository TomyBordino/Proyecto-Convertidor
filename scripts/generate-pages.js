/*
 * Genera las páginas HTML del sitio (index.html + una landing page por
 * herramienta) a partir de index.html como plantilla base y la config en
 * pages-config.js. El sitio publicado sigue siendo HTML/CSS/JS estático
 * plano: este script es solo una herramienta de autor, no corre en
 * producción ni en el navegador del usuario.
 *
 * Uso: node scripts/generate-pages.js   (desde la raíz del proyecto)
 */

const fs = require("fs");
const path = require("path");
const { PAGES, SITE_URL } = require("./pages-config");

const ROOT = path.join(__dirname, "..");
const BASE_HTML = fs.readFileSync(path.join(ROOT, "index.html"), "utf8");

// Strings actuales de index.html que se reemplazan por página.
const CURRENT = {
  title: "ConvertiYa — Comprimir Imágenes y Convertir Archivos Gratis",
  description:
    "Herramientas gratis para comprimir imágenes, convertir HEIC/PDF/audio/fuentes y más — todo 100% en tu navegador, sin subir archivos a ningún servidor.",
  twitterDescription:
    "Herramientas gratis para comprimir imágenes, convertir HEIC/PDF/audio/fuentes y más — todo 100% en tu navegador.",
  canonical: `${SITE_URL}/`,
  h1: '<h1>Convertí tus archivos <span class="accent">gratis y al instante</span>, sin instalar nada</h1>',
  intro:
    '<p>Todo el procesamiento ocurre en tu propio navegador: tus archivos <strong>nunca se suben a ningún servidor</strong>, así que es privado y funciona al instante.</p>',
};

function buildOtherToolsSection(currentPage) {
  const others = PAGES.filter((p) => p.id !== currentPage.id);
  const cards = others
    .map(
      (p) => `      <a class="other-tool-card" href="${p.file}">
        <strong>${p.cardTitle}</strong>
        <span>${p.cardDesc}</span>
      </a>`
    )
    .join("\n");

  return `  <section id="mas-herramientas" class="info-section container">
    <h2>Más herramientas</h2>
    <div class="other-tools-grid">
${cards}
    </div>
  </section>

`;
}

function replaceOrThrow(html, search, replacement, label) {
  if (!html.includes(search)) {
    throw new Error(`No se encontró el string esperado para "${label}". Revisá CURRENT en generate-pages.js contra index.html.`);
  }
  return html.split(search).join(replacement);
}

function generatePage(page) {
  const url = page.file === "index.html" ? `${SITE_URL}/` : `${SITE_URL}/${page.file}`;
  const h1 = `<h1>${page.h1pre} <span class="accent">${page.h1accent}</span>${page.h1post}</h1>`;
  const intro = `<p>${page.intro}</p>`;

  let html = BASE_HTML;
  html = replaceOrThrow(html, `<title>${CURRENT.title}</title>`, `<title>${page.title}</title>`, "title");
  html = replaceOrThrow(
    html,
    `<meta name="description" content="${CURRENT.description}">`,
    `<meta name="description" content="${page.description}">`,
    "meta description"
  );
  html = replaceOrThrow(
    html,
    `<link rel="canonical" href="${CURRENT.canonical}">`,
    `<link rel="canonical" href="${url}">`,
    "canonical"
  );
  html = replaceOrThrow(
    html,
    `<meta property="og:title" content="${CURRENT.title}">`,
    `<meta property="og:title" content="${page.title}">`,
    "og:title"
  );
  html = replaceOrThrow(
    html,
    `<meta property="og:description" content="${CURRENT.description}">`,
    `<meta property="og:description" content="${page.description}">`,
    "og:description"
  );
  html = replaceOrThrow(
    html,
    `<meta property="og:url" content="${CURRENT.canonical}">`,
    `<meta property="og:url" content="${url}">`,
    "og:url"
  );
  html = replaceOrThrow(
    html,
    `<meta name="twitter:title" content="${CURRENT.title}">`,
    `<meta name="twitter:title" content="${page.title}">`,
    "twitter:title"
  );
  html = replaceOrThrow(
    html,
    `<meta name="twitter:description" content="${CURRENT.twitterDescription}">`,
    `<meta name="twitter:description" content="${page.description}">`,
    "twitter:description"
  );
  html = replaceOrThrow(html, "<body>", `<body data-default-tab="${page.tab}">`, "body tag");
  html = replaceOrThrow(html, CURRENT.h1, h1, "hero h1");
  html = replaceOrThrow(html, CURRENT.intro, intro, "hero intro");
  html = replaceOrThrow(
    html,
    '  <section id="como-funciona"',
    `${buildOtherToolsSection(page)}  <section id="como-funciona"`,
    "insertar sección de otras herramientas"
  );

  fs.writeFileSync(path.join(ROOT, page.file), html);
  console.log(`Generado: ${page.file}`);
}

PAGES.forEach(generatePage);

// Regenera también el sitemap con todas las páginas.
const urlEntries = PAGES.map((p) => {
  const loc = p.file === "index.html" ? `${SITE_URL}/` : `${SITE_URL}/${p.file}`;
  const priority = p.file === "index.html" ? "1.0" : "0.8";
  return `  <url>\n    <loc>${loc}</loc>\n    <changefreq>weekly</changefreq>\n    <priority>${priority}</priority>\n  </url>`;
}).concat([
  `  <url>\n    <loc>${SITE_URL}/privacy.html</loc>\n    <changefreq>yearly</changefreq>\n    <priority>0.3</priority>\n  </url>`,
  `  <url>\n    <loc>${SITE_URL}/terms.html</loc>\n    <changefreq>yearly</changefreq>\n    <priority>0.3</priority>\n  </url>`,
]);

const sitemap = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urlEntries.join("\n")}\n</urlset>\n`;
fs.writeFileSync(path.join(ROOT, "sitemap.xml"), sitemap);
console.log("Generado: sitemap.xml");
