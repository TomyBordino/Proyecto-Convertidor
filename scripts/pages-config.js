/*
 * Configuración de las páginas del sitio. Cada entrada (salvo "home")
 * genera un archivo .html dedicado a una sola herramienta, con su propio
 * título/meta/H1 para SEO, pero cargando el mismo motor compartido
 * (assets/js/converters.js y main.js).
 *
 * Para agregar o editar una página: modificá esta lista y corré
 * `node scripts/generate-pages.js` desde la raíz del proyecto.
 */

const SITE_URL = "https://convertiya.netlify.app";

const PAGES = [
  {
    id: "home",
    file: "index.html",
    tab: "compress",
    title: "ConvertiYa — Herramientas Gratis para Convertir y Comprimir Archivos",
    description:
      "Convertí y comprimí imágenes, PDF, audio, fuentes y documentos gratis, 100% en tu navegador. Sin subir archivos a ningún servidor, sin instalar nada.",
    h1pre: "Convertí y comprimí tus archivos",
    h1accent: "gratis y al instante",
    h1post: ", sin instalar nada",
    intro:
      "Todo el procesamiento ocurre en tu propio navegador: tus archivos <strong>nunca se suben a ningún servidor</strong>, así que es privado y funciona al instante.",
    cardTitle: "ConvertiYa",
    cardDesc: "Todas las herramientas, en un solo lugar",
  },
  {
    id: "compress",
    file: "comprimir-imagenes.html",
    tab: "compress",
    title: "Comprimir Imágenes Online Gratis (JPG, PNG, HEIC) — ConvertiYa",
    description:
      "Reducí el peso de tus fotos JPG, PNG, WEBP o HEIC sin perder calidad. Gratis, sin límites, y 100% en tu navegador, sin subir nada a un servidor.",
    h1pre: "Comprimí imágenes online",
    h1accent: "gratis y sin perder calidad",
    h1post: "",
    intro:
      "Ideal para bajar el peso de fotos antes de subirlas a la web, mandarlas por WhatsApp o adjuntarlas en un mail. <strong>Tus fotos nunca se suben a ningún servidor</strong>: todo pasa en tu navegador.",
    cardTitle: "Comprimir imágenes",
    cardDesc: "Reducí el peso de tus fotos sin perder calidad",
  },
  {
    id: "img2img",
    file: "convertir-imagenes.html",
    tab: "img2img",
    title: "Convertir Imágenes Online: PNG, JPG, WEBP, HEIC — ConvertiYa",
    description:
      "Convertí imágenes entre PNG, JPG, WEBP y SVG, o pasá fotos HEIC de iPhone a JPG. Gratis, rápido y sin instalar nada.",
    h1pre: "Convertí imágenes online:",
    h1accent: "PNG, JPG, WEBP y HEIC",
    h1post: "",
    intro:
      "Pasá tus fotos de HEIC (iPhone) a JPG, de PNG a JPG, o al formato que necesites. <strong>Todo se procesa en tu navegador</strong>, sin subir archivos a ningún servidor.",
    cardTitle: "Convertir imágenes",
    cardDesc: "PNG, JPG, WEBP, HEIC y SVG",
  },
  {
    id: "img2pdf",
    file: "imagenes-a-pdf.html",
    tab: "img2pdf",
    title: "Convertir Imágenes a PDF Gratis Online — ConvertiYa",
    description:
      "Convertí tus fotos JPG, PNG o HEIC a un archivo PDF único, gratis y sin instalar nada.",
    h1pre: "Convertí imágenes a PDF",
    h1accent: "gratis y al instante",
    h1post: "",
    intro:
      "Subí una o varias fotos y armá un solo PDF, en el orden que elijas. <strong>Tus imágenes nunca se suben a ningún servidor</strong>: la conversión ocurre en tu navegador.",
    cardTitle: "Imágenes a PDF",
    cardDesc: "Combiná varias fotos en un solo PDF",
  },
  {
    id: "pdf2img",
    file: "pdf-a-imagenes.html",
    tab: "pdf2img",
    title: "Convertir PDF a JPG o PNG Gratis Online — ConvertiYa",
    description:
      "Extraé cada página de un PDF como imagen JPG o PNG en alta calidad, gratis y online.",
    h1pre: "Convertí un PDF a",
    h1accent: "JPG o PNG",
    h1post: "",
    intro:
      "Cada página de tu PDF se exporta como una imagen individual en alta calidad. <strong>Todo pasa en tu navegador</strong>, sin subir el archivo a ningún servidor.",
    cardTitle: "PDF a imágenes",
    cardDesc: "Cada página como una imagen JPG o PNG",
  },
  {
    id: "audio",
    file: "convertidor-de-audio.html",
    tab: "audio",
    title: "Convertidor de Audio a MP3 y WAV Gratis — ConvertiYa",
    description:
      "Convertí audio a MP3 o WAV, o extraé el audio de un video MP4. Gratis y 100% en tu navegador.",
    h1pre: "Convertidor de audio:",
    h1accent: "a MP3, WAV, o desde un video",
    h1post: "",
    intro:
      "Convertí cualquier audio que tu navegador pueda reproducir, o subí un video (MP4, MOV, WEBM) para extraer su pista de audio. <strong>Nunca se sube nada a un servidor</strong>.",
    cardTitle: "Convertidor de audio",
    cardDesc: "A MP3 o WAV, o extraído de un video",
  },
  {
    id: "font",
    file: "convertidor-de-fuentes.html",
    tab: "font",
    title: "Convertidor de Fuentes TTF a WOFF Gratis — ConvertiYa",
    description:
      "Convertí tipografías TTF u OTF a WOFF para usarlas en la web, o un WOFF a TTF/OTF para instalarlo. Gratis.",
    h1pre: "Convertidor de fuentes:",
    h1accent: "TTF, OTF y WOFF",
    h1post: "",
    intro:
      "Convertí una fuente TTF/OTF a WOFF para tu sitio web, o un WOFF descargado a TTF/OTF para instalarlo en tu computadora. <strong>Todo en tu navegador</strong>, sin subir el archivo.",
    cardTitle: "Convertidor de fuentes",
    cardDesc: "TTF y OTF a WOFF para la web",
  },
  {
    id: "document",
    file: "convertidor-de-documentos.html",
    tab: "document",
    title: "Convertir PDF a Word Gratis Online — ConvertiYa",
    description:
      "Convertí PDF a Word (.docx) o a texto, y TXT/DOCX a PDF. Gratis, sin registrarte.",
    h1pre: "Convertí PDF a Word,",
    h1accent: "gratis y online",
    h1post: "",
    intro:
      "Subí un PDF y elegí si querés el texto plano o un archivo Word (.docx), o convertí un TXT/DOCX a PDF. <strong>Sin subir tu documento a ningún servidor</strong>.",
    cardTitle: "Convertidor de documentos",
    cardDesc: "PDF a Word, o TXT/DOCX a PDF",
  },
  {
    id: "units",
    file: "convertidor-de-unidades.html",
    tab: "units",
    title: "Convertidor de Unidades Online Gratis — ConvertiYa",
    description:
      "Convertí longitud, peso, volumen y temperatura al instante: metros a pies, kilos a libras, Celsius a Fahrenheit y más.",
    h1pre: "Convertidor de unidades:",
    h1accent: "longitud, peso y temperatura",
    h1post: "",
    intro:
      "Una calculadora simple para convertir metros a pies, kilogramos a libras, litros a galones o Celsius a Fahrenheit, al instante y sin anuncios molestos.",
    cardTitle: "Convertidor de unidades",
    cardDesc: "Longitud, peso, volumen y temperatura",
  },
  {
    id: "time",
    file: "convertidor-de-zona-horaria.html",
    tab: "time",
    title: "Convertidor de Zona Horaria Online Gratis — ConvertiYa",
    description:
      "Convertí una fecha y hora entre husos horarios de todo el mundo: Argentina, España, México, Estados Unidos y más.",
    h1pre: "Convertidor de zona horaria",
    h1accent: "y husos horarios",
    h1post: "",
    intro:
      "Convertí una fecha y hora de un huso horario a otro para coordinar reuniones o llamadas internacionales, calculado con precisión al instante.",
    cardTitle: "Convertidor de zona horaria",
    cardDesc: "Convertí horarios entre países",
  },
];

module.exports = { PAGES, SITE_URL };
