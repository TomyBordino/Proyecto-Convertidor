/*
 * Genera las páginas HTML del sitio (index.html + una landing page por
 * herramienta) a partir de index.html como plantilla base y la config en
 * pages-config.js. El sitio publicado sigue siendo HTML/CSS/JS estático
 * plano: este script es solo una herramienta de autor, no corre en
 * producción ni en el navegador del usuario.
 *
 * El script es idempotente: usa patrones (no texto literal exacto) para
 * encontrar cada bloque a reemplazar, así que es seguro correrlo una y
 * otra vez aunque index.html ya tenga aplicado el contenido de una
 * generación anterior (incluida la sección "Más herramientas", que se
 * quita y se vuelve a insertar en cada corrida en vez de acumularse).
 *
 * Uso: node scripts/generate-pages.js   (desde la raíz del proyecto)
 */

const fs = require("fs");
const path = require("path");
const { PAGES, SITE_URL } = require("./pages-config");

const ROOT = path.join(__dirname, "..");
const BASE_HTML = fs.readFileSync(path.join(ROOT, "index.html"), "utf8");

function replaceOrThrow(html, pattern, replacement, label) {
  if (!pattern.test(html)) {
    throw new Error(`No se encontró el patrón esperado para "${label}". Revisá la estructura de index.html.`);
  }
  return html.replace(pattern, replacement);
}

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

function generatePage(page) {
  const url = page.file === "index.html" ? `${SITE_URL}/` : `${SITE_URL}/${page.file}`;
  const h1 = `<h1>${page.h1pre} <span class="accent">${page.h1accent}</span>${page.h1post}</h1>`;

  let html = BASE_HTML;

  // Quitar cualquier sección "Más herramientas" ya insertada por una
  // corrida anterior, para no acumular duplicados.
  html = html.replace(/[ \t]*<section id="mas-herramientas"[\s\S]*?<\/section>\s*\n/, "");

  html = replaceOrThrow(html, /<title>[\s\S]*?<\/title>/, `<title>${page.title}</title>`, "title");
  html = replaceOrThrow(
    html,
    /<meta name="description" content="[^"]*">/,
    `<meta name="description" content="${page.description}">`,
    "meta description"
  );
  html = replaceOrThrow(
    html,
    /<link rel="canonical" href="[^"]*">/,
    `<link rel="canonical" href="${url}">`,
    "canonical"
  );
  html = replaceOrThrow(
    html,
    /<meta property="og:title" content="[^"]*">/,
    `<meta property="og:title" content="${page.title}">`,
    "og:title"
  );
  html = replaceOrThrow(
    html,
    /<meta property="og:description" content="[^"]*">/,
    `<meta property="og:description" content="${page.description}">`,
    "og:description"
  );
  html = replaceOrThrow(
    html,
    /<meta property="og:url" content="[^"]*">/,
    `<meta property="og:url" content="${url}">`,
    "og:url"
  );
  html = replaceOrThrow(
    html,
    /<meta name="twitter:title" content="[^"]*">/,
    `<meta name="twitter:title" content="${page.title}">`,
    "twitter:title"
  );
  html = replaceOrThrow(
    html,
    /<meta name="twitter:description" content="[^"]*">/,
    `<meta name="twitter:description" content="${page.description}">`,
    "twitter:description"
  );
  html = replaceOrThrow(
    html,
    /<body(?:\s+data-default-tab="[^"]*")?>/,
    `<body data-default-tab="${page.tab}">`,
    "body tag"
  );
  html = replaceOrThrow(html, /<h1>[\s\S]*?<\/h1>/, h1, "hero h1");
  html = replaceOrThrow(
    html,
    /(<\/h1>\s*)<p>[\s\S]*?<\/p>(\s*<div class="hero-trust">)/,
    `$1<p>${page.intro}</p>$2`,
    "hero intro"
  );
  html = replaceOrThrow(
    html,
    /  <section id="como-funciona"/,
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
