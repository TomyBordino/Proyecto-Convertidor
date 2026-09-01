# ConvertiYa — Convertidor de archivos online

Sitio web estático que permite convertir archivos directamente en el navegador
(sin backend, sin subir archivos a ningún servidor) y que se monetiza mostrando
anuncios (Google AdSense).

## Herramientas incluidas

1. **Convertir imágenes**: PNG ⇄ JPG ⇄ WEBP.
2. **Imágenes a PDF**: combina varias imágenes en un único PDF.
3. **PDF a imágenes**: exporta cada página de un PDF como PNG o JPG.

Todo el procesamiento ocurre con `<canvas>`, [pdf.js](https://mozilla.github.io/pdf.js/),
[jsPDF](https://github.com/parallax/jsPDF) y [JSZip](https://stuk.github.io/jszip/),
cargados desde CDN. No hay build step: es HTML/CSS/JS plano.

## Estructura del proyecto

```
index.html          → página principal con las 3 herramientas
privacy.html         → política de privacidad (requerida por AdSense)
terms.html            → términos de uso
ads.txt               → archivo requerido por Google AdSense
assets/css/style.css  → estilos
assets/js/converters.js → funciones de conversión (sin DOM)
assets/js/main.js      → lógica de interfaz (tabs, dropzones, descargas)
assets/img/favicon.svg → ícono del sitio
```

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

## Próximos pasos sugeridos

- Agregar más conversiones (ej. audio, video, comprimir imágenes).
- Agregar Google Analytics para medir tráfico.
- Comprar un dominio propio (mejora la aprobación y confianza de AdSense).
- Completar `[COMPLETAR FECHA]` y `[COMPLETAR EMAIL DE CONTACTO]` en
  `privacy.html` y `terms.html`.
