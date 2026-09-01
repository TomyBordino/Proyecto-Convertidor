# ConvertiYa — Convertidor de archivos online

Sitio web estático que permite convertir archivos directamente en el navegador
(sin backend, sin subir archivos a ningún servidor) y que se monetiza mostrando
anuncios (Google AdSense).

## Herramientas incluidas

1. **Comprimir imágenes**: reduce el peso de fotos (incluye HEIC/HEIF de iPhone) controlando calidad y ancho máximo.
2. **Convertir imágenes**: PNG ⇄ JPG ⇄ WEBP ⇄ SVG (embebida), con soporte de entrada HEIC/HEIF/JFIF.
3. **Imágenes a PDF**: combina varias imágenes en un único PDF.
4. **PDF a imágenes**: exporta cada página de un PDF como PNG o JPG.
5. **Convertidor de audio**: cualquier audio (o el audio de un video MP4/MOV/WEBM) a WAV o MP3.
6. **Convertidor de fuentes**: TTF/OTF ⇄ WOFF.
7. **Convertidor de documentos**: TXT/MD/DOCX ⇄ PDF, y PDF → TXT o DOCX (solo texto, sin formato avanzado).
8. **Convertidor de unidades**: longitud, peso, volumen y temperatura.
9. **Convertidor de zona horaria**: convierte una fecha/hora entre husos horarios usando la API `Intl` del navegador.

Todo el procesamiento ocurre con `<canvas>`, Web Audio API, `Intl`,
[pdf.js](https://mozilla.github.io/pdf.js/), [jsPDF](https://github.com/parallax/jsPDF),
[JSZip](https://stuk.github.io/jszip/), [pako](https://github.com/nodeca/pako),
[lamejs](https://github.com/zhuker/lamejs) y [heic2any](https://github.com/alexcorvi/heic2any),
todos cargados desde CDN. No hay build step: es HTML/CSS/JS plano.

**Pendiente / fuera de alcance por ahora**: conversión real de video (ej. MOV a MP4)
y video/imagen ⇄ GIF, porque requieren un motor pesado (~decenas de MB) tipo
ffmpeg.wasm; y EPUB, por la complejidad de parsear bien el formato. Ver
`assets/js/converters.js` si querés retomarlos.

## Estructura del proyecto

```
index.html                          → hub / home (las 9 herramientas)
comprimir-imagenes.html             → landing dedicada, SEO
convertir-imagenes.html             → landing dedicada, SEO
imagenes-a-pdf.html                 → landing dedicada, SEO
pdf-a-imagenes.html                 → landing dedicada, SEO
convertidor-de-audio.html           → landing dedicada, SEO
convertidor-de-fuentes.html         → landing dedicada, SEO
convertidor-de-documentos.html      → landing dedicada, SEO
convertidor-de-unidades.html        → landing dedicada, SEO
convertidor-de-zona-horaria.html    → landing dedicada, SEO
privacy.html                        → política de privacidad (requerida por AdSense)
terms.html                           → términos de uso
ads.txt                              → archivo requerido por Google AdSense
robots.txt / sitemap.xml             → SEO técnico
assets/css/style.css                 → estilos
assets/js/converters.js              → funciones de conversión (sin DOM)
assets/js/main.js                    → lógica de interfaz (tabs, dropzones, descargas)
assets/img/favicon.svg               → ícono del sitio
scripts/pages-config.js              → metadatos (título, meta, H1) de cada landing
scripts/generate-pages.js            → genera las 9 landing pages + sitemap.xml
```

### Landing pages por herramienta

Las 10 páginas HTML comparten exactamente el mismo motor
(`assets/js/converters.js` y `main.js`) y el mismo contenido — las 9
herramientas siguen viviendo todas como pestañas en cada página. Lo que
cambia por página es: `<title>`, meta descripción, `canonical`, Open Graph,
el H1 y el párrafo de introducción, y qué pestaña abre por defecto
(`<body data-default-tab="...">`, leído por `main.js`). Así cada URL puede
posicionar para su propia búsqueda ("comprimir imagen online", "pdf a word
gratis", etc.) sin duplicar la lógica de conversión.

**Estas páginas NO se editan a mano.** Se generan con un script:

```bash
node scripts/generate-pages.js
```

El script toma `index.html` como plantilla base y aplica los reemplazos
definidos en `scripts/pages-config.js` (uno por herramienta), y regenera
`sitemap.xml` con todas las URLs. Flujo de trabajo:

1. Para cambiar algo compartido entre todas las páginas (una herramienta,
   el header, el FAQ, el CSS): editá `index.html` / `assets/*` como siempre,
   y después corré `node scripts/generate-pages.js` para propagar el cambio
   a las 9 landing pages.
2. Para cambiar el título/meta/H1 de una sola herramienta: editá su entrada
   en `scripts/pages-config.js` y volvé a correr el script.
3. Para agregar una herramienta nueva: agregale su panel/tab en `index.html`
   como las demás, sumale una entrada en `pages-config.js`, y corré el script.

Sigue siendo un sitio 100% estático (HTML/CSS/JS plano, sin backend): el
script de generación es una herramienta de autor que corrés vos (o yo)
antes de subir cambios, no algo que corra en producción ni en el navegador
del usuario.

## Cómo probarlo localmente

No hace falta instalar nada. Podés abrir `index.html` directamente en el
navegador, aunque algunas cosas (como los módulos o fetch de archivos locales)
funcionan mejor sirviendo el sitio con un servidor simple:

```bash
python3 -m http.server 8080
# abrí http://localhost:8080
```

## Despliegue gratuito

Al ser un sitio 100% estático, podés publicarlo gratis en cualquiera de estos
servicios (elegí uno):

- **GitHub Pages**: Settings → Pages → Deploy from branch → elegí la rama y
  la carpeta raíz.
- **Netlify** / **Vercel** / **Cloudflare Pages**: conectá el repositorio y
  desplegá sin configuración adicional (no hay build command).

## Monetización con anuncios (Google AdSense)

1. Creá una cuenta en [Google AdSense](https://www.google.com/adsense/).
2. Agregá tu sitio ya desplegado (con dominio propio o el que te da el
   hosting) y esperá la aprobación. AdSense suele requerir:
   - Contenido original suficiente (ya incluido: hero, cómo funciona, FAQ).
   - Página de **Política de privacidad** (`privacy.html`) — ya incluida.
   - Página de **Términos de uso** (`terms.html`) — ya incluida.
   - Tráfico real y cumplimiento de sus políticas de contenido.
3. Una vez aprobado, AdSense te da un **ID de cliente** con el formato
   `ca-pub-XXXXXXXXXXXXXXXX`. Reemplazá todas las apariciones de
   `ca-pub-XXXXXXXXXXXXXXXX` en `index.html` (y en `privacy.html`/`terms.html`
   si les agregás anuncios) por tu ID real.
4. Creá "unidades de anuncio" (Ad units) en el panel de AdSense y reemplazá
   los `data-ad-slot="000000000X"` de ejemplo por los IDs reales de cada
   unidad.
5. Copiá el snippet que AdSense te da para `ads.txt` y pegalo en el archivo
   `ads.txt` de la raíz del sitio (reemplazando el comentario de ejemplo).
   Sin este archivo correctamente configurado, AdSense no muestra anuncios.
6. Los anuncios se cargan de forma diferida/normal vía el script oficial de
   AdSense; no hace falta ningún cambio de código adicional.

### Ubicación de los espacios publicitarios

Ya están colocados 4 espacios en `index.html`, pensados para no interferir
con la experiencia de conversión (cumpliendo las políticas de AdSense sobre
clics accidentales):

- Banner superior (debajo del header).
- Barra lateral junto a las herramientas (solo escritorio).
- Bloque intermedio, entre las herramientas y la sección "Cómo funciona".
- Pie de página.

### Alternativas a AdSense

Si tu sitio es nuevo y AdSense todavía no te aprueba, podés considerar redes
alternativas mientras generás tráfico: Media.net, Ezoic o PropellerAds. La
integración es similar: reemplazar los bloques `<ins class="adsbygoogle">`
por el snippet que te dé la red elegida.

## SEO

Ya implementado:

- `robots.txt` y `sitemap.xml` en la raíz del sitio.
- `<title>` y meta descripción optimizados con palabras clave, en cada página.
- `<link rel="canonical">` en todas las páginas.
- Open Graph y Twitter Card para que se vea bien al compartir en redes.
- Datos estructurados (JSON-LD) `WebApplication` y `FAQPage` en `index.html`
  — esto habilita resultados enriquecidos (rich snippets) en Google. **Importante:**
  si editás el FAQ visible, el texto tiene que coincidir exactamente con el
  JSON-LD del `<head>`, o Google puede dejar de mostrar el rich snippet.
- Descripciones de cada herramienta reescritas con términos de búsqueda reales
  (ej. "PDF a Word", "HEIC a JPG", "Celsius a Fahrenheit").

### Pasos manuales que solo vos podés hacer

1. **Dar de alta el sitio en [Google Search Console](https://search.google.com/search-console)**
   y enviar `https://convertiya.netlify.app/sitemap.xml` — esto acelera muchísimo
   que Google empiece a indexar el sitio.
2. Ídem en [Bing Webmaster Tools](https://www.bing.com/webmasters).
3. Conseguir **backlinks**: publicalo en foros, Reddit, directorios de herramientas
   gratuitas ("free tools directories"), y compartilo en redes. Los backlinks
   siguen siendo uno de los factores de ranking más importantes.
4. Considerar comprar un dominio propio (ej. `convertiya.com`) — genera más
   confianza que un subdominio de `.netlify.app`, tanto para SEO como para la
   aprobación de AdSense.

### Landing pages por herramienta (ya implementado)

Cada herramienta tiene su propia URL dedicada (`comprimir-imagenes.html`,
`convertidor-de-audio.html`, etc.), con título, meta descripción, H1 y texto
introductorio enfocados en esa conversión puntual — mientras reutilizan el
mismo motor de conversión (`assets/js/converters.js`). Es el patrón que usan
Smallpdf, iLovePDF o Convertio. Ver la sección "Landing pages por
herramienta" más arriba para cómo mantenerlas (se generan con
`node scripts/generate-pages.js`, no se editan a mano).

## Próximos pasos sugeridos

- Agregar Google Analytics para medir tráfico.
- Comprar un dominio propio (mejora la aprobación y confianza de AdSense).
- Completar `[COMPLETAR FECHA]` y `[COMPLETAR EMAIL DE CONTACTO]` en
  `privacy.html` y `terms.html`.
