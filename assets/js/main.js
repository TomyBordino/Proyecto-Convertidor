/* Lógica de interfaz: tabs, dropzones, listas de archivos y disparo de conversiones. */

document.getElementById("year").textContent = new Date().getFullYear();

// Muchos navegadores no le asignan un MIME type a los archivos HEIC/HEIF
// (file.type queda vacío), así que además revisamos la extensión.
function isImageFile(file) {
  return file.type.startsWith("image/") || /\.(heic|heif)$/i.test(file.name);
}

// ---------- Tabs ----------
const tabButtons = document.querySelectorAll(".tab-btn");
const panels = document.querySelectorAll(".tool-panel");

function activateTab(tabKey) {
  tabButtons.forEach((b) => {
    const isTarget = b.dataset.tab === tabKey;
    b.classList.toggle("active", isTarget);
    b.setAttribute("aria-selected", isTarget ? "true" : "false");
  });
  panels.forEach((p) => p.classList.toggle("active", p.id === "panel-" + tabKey));
}

// Cada pestaña tiene su propia landing page dedicada (data-href). Si ya
// estás viendo esa herramienta no hace falta navegar; si no, la pestaña
// te lleva a su URL real en vez de solo cambiar el panel en la página
// actual, así el navegador (y Google) siempre reflejan la herramienta
// que se está mostrando.
const currentFile = location.pathname.split("/").pop() || "index.html";

tabButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    if (btn.classList.contains("active")) return;
    const href = btn.dataset.href;
    if (href && href !== currentFile) {
      window.location.href = href;
      return;
    }
    activateTab(btn.dataset.tab);
  });
});

// Cada landing page dedicada declara su herramienta principal en
// <body data-default-tab="..."> para que abra directamente en esa pestaña.
if (document.body.dataset.defaultTab) {
  activateTab(document.body.dataset.defaultTab);
}

// ---------- Helper: dropzone + input genérico ----------
function setupDropzone(dropzoneId, inputId, onFilesSelected) {
  const dropzone = document.getElementById(dropzoneId);
  const input = document.getElementById(inputId);

  const triggerBtn = document.querySelector(`[data-trigger="${inputId}"]`);
  if (triggerBtn) triggerBtn.addEventListener("click", () => input.click());

  dropzone.addEventListener("click", (e) => {
    if (!e.target.closest("button")) input.click();
  });

  input.addEventListener("change", () => onFilesSelected(Array.from(input.files)));

  ["dragenter", "dragover"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    })
  );
  ["dragleave", "drop"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
    })
  );
  dropzone.addEventListener("drop", (e) => {
    const files = Array.from(e.dataTransfer.files);
    onFilesSelected(files);
  });
}

function renderFileList(listEl, files) {
  listEl.innerHTML = "";
  files.forEach((file) => {
    const li = document.createElement("li");
    li.innerHTML = `<span>${file.name}</span><span class="file-size">${Converters.formatBytes(file.size)}</span>`;
    listEl.appendChild(li);
  });
}

function downloadBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

function renderImageResults(container, items, { zipName }) {
  container.innerHTML = "";

  if (items.length > 1) {
    const toolbar = document.createElement("div");
    toolbar.className = "results-toolbar";
    const zipBtn = document.createElement("button");
    zipBtn.className = "btn btn-secondary";
    zipBtn.textContent = "Descargar todo (.zip)";
    zipBtn.addEventListener("click", async () => {
      zipBtn.disabled = true;
      zipBtn.textContent = "Comprimiendo...";
      const zip = await Converters.zipFiles(items, zipName);
      downloadBlob(zip.blob, zip.name);
      zipBtn.disabled = false;
      zipBtn.textContent = "Descargar todo (.zip)";
    });
    toolbar.appendChild(zipBtn);
    container.appendChild(toolbar);
  }

  items.forEach((item) => {
    const card = document.createElement("div");
    card.className = "result-card";
    const url = URL.createObjectURL(item.blob);
    card.innerHTML = `
      <img src="${url}" alt="${item.name}">
      <div class="result-name">${item.name}</div>
    `;
    const btn = document.createElement("button");
    btn.className = "btn btn-download";
    btn.textContent = "Descargar";
    btn.addEventListener("click", () => downloadBlob(item.blob, item.name));
    card.appendChild(btn);
    container.appendChild(card);
  });
}

function renderCompressResults(container, items, { zipName }) {
  container.innerHTML = "";

  if (items.length > 1) {
    const toolbar = document.createElement("div");
    toolbar.className = "results-toolbar";
    const zipBtn = document.createElement("button");
    zipBtn.className = "btn btn-secondary";
    zipBtn.textContent = "Descargar todo (.zip)";
    zipBtn.addEventListener("click", async () => {
      zipBtn.disabled = true;
      zipBtn.textContent = "Comprimiendo...";
      const zip = await Converters.zipFiles(items, zipName);
      downloadBlob(zip.blob, zip.name);
      zipBtn.disabled = false;
      zipBtn.textContent = "Descargar todo (.zip)";
    });
    toolbar.appendChild(zipBtn);
    container.appendChild(toolbar);
  }

  items.forEach((item) => {
    const card = document.createElement("div");
    card.className = "result-card";
    const url = URL.createObjectURL(item.blob);
    const reduction = Math.max(0, Math.round((1 - item.blob.size / item.originalSize) * 100));
    card.innerHTML = `
      <img src="${url}" alt="${item.name}">
      <div class="result-name">${item.name}</div>
      <div class="result-savings">${Converters.formatBytes(item.originalSize)} → ${Converters.formatBytes(item.blob.size)} <strong>(-${reduction}%)</strong></div>
    `;
    const btn = document.createElement("button");
    btn.className = "btn btn-download";
    btn.textContent = "Descargar";
    btn.addEventListener("click", () => downloadBlob(item.blob, item.name));
    card.appendChild(btn);
    container.appendChild(card);
  });
}

function renderFileResults(container, items, { zipName }) {
  container.innerHTML = "";

  if (items.length > 1) {
    const toolbar = document.createElement("div");
    toolbar.className = "results-toolbar";
    const zipBtn = document.createElement("button");
    zipBtn.className = "btn btn-secondary";
    zipBtn.textContent = "Descargar todo (.zip)";
    zipBtn.addEventListener("click", async () => {
      zipBtn.disabled = true;
      zipBtn.textContent = "Comprimiendo...";
      const zip = await Converters.zipFiles(items, zipName);
      downloadBlob(zip.blob, zip.name);
      zipBtn.disabled = false;
      zipBtn.textContent = "Descargar todo (.zip)";
    });
    toolbar.appendChild(zipBtn);
    container.appendChild(toolbar);
  }

  items.forEach((item) => {
    const card = document.createElement("div");
    card.className = "result-card";
    card.innerHTML = `
      <div class="result-name">${item.name}</div>
      <div class="result-savings">${Converters.formatBytes(item.blob.size)}</div>
    `;
    const btn = document.createElement("button");
    btn.className = "btn btn-download";
    btn.textContent = "Descargar";
    btn.addEventListener("click", () => downloadBlob(item.blob, item.name));
    card.appendChild(btn);
    container.appendChild(card);
  });
}

function renderPdfResult(container, item) {
  container.innerHTML = "";
  const card = document.createElement("div");
  card.className = "result-card";
  card.innerHTML = `<div class="result-name">${item.name} — ${Converters.formatBytes(item.blob.size)}</div>`;
  const btn = document.createElement("button");
  btn.className = "btn btn-download";
  btn.textContent = "Descargar PDF";
  btn.addEventListener("click", () => downloadBlob(item.blob, item.name));
  card.appendChild(btn);
  container.appendChild(card);
}

// ============================================================
// Herramienta 0: Comprimir imágenes
// ============================================================
(() => {
  let selectedFiles = [];
  const fileListEl = document.getElementById("compress-filelist");
  const convertBtn = document.getElementById("btn-compress-convert");
  const resultsEl = document.getElementById("compress-results");
  const qualityInput = document.getElementById("compress-quality");
  const qualityVal = document.getElementById("compress-quality-val");
  const maxWidthSelect = document.getElementById("compress-maxwidth");

  qualityInput.addEventListener("input", () => (qualityVal.textContent = qualityInput.value));

  setupDropzone("dropzone-compress", "input-compress", (files) => {
    selectedFiles = files.filter((f) => isImageFile(f));
    renderFileList(fileListEl, selectedFiles);
    convertBtn.disabled = selectedFiles.length === 0;
    resultsEl.innerHTML = "";
  });

  convertBtn.addEventListener("click", async () => {
    convertBtn.disabled = true;
    convertBtn.textContent = "Comprimiendo...";
    resultsEl.innerHTML = "";
    try {
      const quality = Number(qualityInput.value) / 100;
      const maxWidth = Number(maxWidthSelect.value);
      const results = [];
      for (const file of selectedFiles) {
        results.push(await Converters.compressImage(file, { quality, maxWidth }));
      }
      renderCompressResults(resultsEl, results, { zipName: "imagenes-comprimidas.zip" });
    } catch (err) {
      alert("Ocurrió un error: " + err.message);
    } finally {
      convertBtn.disabled = false;
      convertBtn.textContent = "Comprimir";
    }
  });
})();

// ============================================================
// Herramienta 1: Imagen -> Imagen
// ============================================================
(() => {
  let selectedFiles = [];
  const fileListEl = document.getElementById("img2img-filelist");
  const convertBtn = document.getElementById("btn-img2img-convert");
  const resultsEl = document.getElementById("img2img-results");
  const formatSelect = document.getElementById("img2img-format");
  const qualityInput = document.getElementById("img2img-quality");
  const qualityVal = document.getElementById("img2img-quality-val");
  const qualityWrap = document.getElementById("img2img-quality-wrap");

  function updateQualityVisibility() {
    qualityWrap.style.display = formatSelect.value === "image/png" ? "none" : "flex";
  }
  formatSelect.addEventListener("change", updateQualityVisibility);
  updateQualityVisibility();

  qualityInput.addEventListener("input", () => (qualityVal.textContent = qualityInput.value));

  setupDropzone("dropzone-img2img", "input-img2img", (files) => {
    selectedFiles = files.filter((f) => isImageFile(f));
    renderFileList(fileListEl, selectedFiles);
    convertBtn.disabled = selectedFiles.length === 0;
    resultsEl.innerHTML = "";
  });

  convertBtn.addEventListener("click", async () => {
    convertBtn.disabled = true;
    convertBtn.textContent = "Convirtiendo...";
    resultsEl.innerHTML = "";
    try {
      const mimeType = formatSelect.value;
      const quality = Number(qualityInput.value) / 100;
      const results = [];
      for (const file of selectedFiles) {
        results.push(await Converters.convertImage(file, mimeType, quality));
      }
      renderImageResults(resultsEl, results, { zipName: "imagenes-convertidas.zip" });
    } catch (err) {
      alert("Ocurrió un error: " + err.message);
    } finally {
      convertBtn.disabled = false;
      convertBtn.textContent = "Convertir";
    }
  });
})();

// ============================================================
// Herramienta 2: Imágenes -> PDF
// ============================================================
(() => {
  let selectedFiles = [];
  const fileListEl = document.getElementById("img2pdf-filelist");
  const convertBtn = document.getElementById("btn-img2pdf-convert");
  const resultsEl = document.getElementById("img2pdf-results");
  const pageSizeSelect = document.getElementById("img2pdf-pagesize");
  const orientationSelect = document.getElementById("img2pdf-orientation");

  setupDropzone("dropzone-img2pdf", "input-img2pdf", (files) => {
    selectedFiles = files.filter((f) => isImageFile(f));
    renderFileList(fileListEl, selectedFiles);
    convertBtn.disabled = selectedFiles.length === 0;
    resultsEl.innerHTML = "";
  });

  convertBtn.addEventListener("click", async () => {
    convertBtn.disabled = true;
    convertBtn.textContent = "Generando...";
    resultsEl.innerHTML = "";
    try {
      const result = await Converters.imagesToPdf(selectedFiles, {
        pageSize: pageSizeSelect.value,
        orientation: orientationSelect.value,
      });
      renderPdfResult(resultsEl, result);
    } catch (err) {
      alert("Ocurrió un error: " + err.message);
    } finally {
      convertBtn.disabled = false;
      convertBtn.textContent = "Generar PDF";
    }
  });
})();

// ============================================================
// Herramienta 3: PDF -> Imágenes
// ============================================================
(() => {
  let selectedFile = null;
  const fileListEl = document.getElementById("pdf2img-filelist");
  const convertBtn = document.getElementById("btn-pdf2img-convert");
  const resultsEl = document.getElementById("pdf2img-results");
  const formatSelect = document.getElementById("pdf2img-format");
  const scaleSelect = document.getElementById("pdf2img-scale");

  setupDropzone("dropzone-pdf2img", "input-pdf2img", (files) => {
    const pdfFile = files.find((f) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf"));
    selectedFile = pdfFile || null;
    renderFileList(fileListEl, selectedFile ? [selectedFile] : []);
    convertBtn.disabled = !selectedFile;
    resultsEl.innerHTML = "";
  });

  convertBtn.addEventListener("click", async () => {
    convertBtn.disabled = true;
    convertBtn.textContent = "Convirtiendo...";
    resultsEl.innerHTML = "";
    try {
      const results = await Converters.pdfToImages(
        selectedFile,
        formatSelect.value,
        Number(scaleSelect.value)
      );
      renderImageResults(resultsEl, results, { zipName: "paginas-pdf.zip" });
    } catch (err) {
      alert("Ocurrió un error: " + err.message);
    } finally {
      convertBtn.disabled = false;
      convertBtn.textContent = "Convertir";
    }
  });
})();

// ============================================================
// Herramienta 4: Audio
// ============================================================
(() => {
  let selectedFiles = [];
  const fileListEl = document.getElementById("audio-filelist");
  const convertBtn = document.getElementById("btn-audio-convert");
  const resultsEl = document.getElementById("audio-results");
  const formatSelect = document.getElementById("audio-format");
  const bitrateSelect = document.getElementById("audio-bitrate");
  const bitrateWrap = document.getElementById("audio-bitrate-wrap");

  function updateBitrateVisibility() {
    bitrateWrap.style.display = formatSelect.value === "mp3" ? "flex" : "none";
  }
  formatSelect.addEventListener("change", updateBitrateVisibility);
  updateBitrateVisibility();

  setupDropzone("dropzone-audio", "input-audio", (files) => {
    selectedFiles = files.filter((f) => f.type.startsWith("audio/") || f.type.startsWith("video/"));
    renderFileList(fileListEl, selectedFiles);
    convertBtn.disabled = selectedFiles.length === 0;
    resultsEl.innerHTML = "";
  });

  convertBtn.addEventListener("click", async () => {
    convertBtn.disabled = true;
    convertBtn.textContent = "Convirtiendo...";
    resultsEl.innerHTML = "";
    try {
      const opts = { format: formatSelect.value, bitrate: Number(bitrateSelect.value) };
      const results = [];
      for (const file of selectedFiles) {
        results.push(await Converters.convertAudio(file, opts));
      }
      renderFileResults(resultsEl, results, { zipName: "audio-convertido.zip" });
    } catch (err) {
      alert("Ocurrió un error: " + err.message);
    } finally {
      convertBtn.disabled = false;
      convertBtn.textContent = "Convertir";
    }
  });
})();

// ============================================================
// Herramienta 5: Fuentes
// ============================================================
(() => {
  let selectedFiles = [];
  const fileListEl = document.getElementById("font-filelist");
  const convertBtn = document.getElementById("btn-font-convert");
  const resultsEl = document.getElementById("font-results");

  setupDropzone("dropzone-font", "input-font", (files) => {
    selectedFiles = files;
    renderFileList(fileListEl, selectedFiles);
    convertBtn.disabled = selectedFiles.length === 0;
    resultsEl.innerHTML = "";
  });

  convertBtn.addEventListener("click", async () => {
    convertBtn.disabled = true;
    convertBtn.textContent = "Convirtiendo...";
    resultsEl.innerHTML = "";
    try {
      const results = [];
      for (const file of selectedFiles) {
        results.push(await Converters.convertFont(file));
      }
      renderFileResults(resultsEl, results, { zipName: "fuentes-convertidas.zip" });
    } catch (err) {
      alert("Ocurrió un error: " + err.message);
    } finally {
      convertBtn.disabled = false;
      convertBtn.textContent = "Convertir";
    }
  });
})();

// ============================================================
// Herramienta 6: Documentos
// ============================================================
(() => {
  let selectedFiles = [];
  const fileListEl = document.getElementById("document-filelist");
  const convertBtn = document.getElementById("btn-document-convert");
  const resultsEl = document.getElementById("document-results");
  const pdfOutputSelect = document.getElementById("document-pdf-output");

  setupDropzone("dropzone-document", "input-document", (files) => {
    selectedFiles = files;
    renderFileList(fileListEl, selectedFiles);
    convertBtn.disabled = selectedFiles.length === 0;
    resultsEl.innerHTML = "";
  });

  convertBtn.addEventListener("click", async () => {
    convertBtn.disabled = true;
    convertBtn.textContent = "Convirtiendo...";
    resultsEl.innerHTML = "";
    try {
      const opts = { pdfOutput: pdfOutputSelect.value };
      const results = [];
      for (const file of selectedFiles) {
        results.push(await Converters.convertDocument(file, opts));
      }
      renderFileResults(resultsEl, results, { zipName: "documentos-convertidos.zip" });
    } catch (err) {
      alert("Ocurrió un error: " + err.message);
    } finally {
      convertBtn.disabled = false;
      convertBtn.textContent = "Convertir";
    }
  });
})();

// ============================================================
// Herramienta 7: Convertidor de unidades
// ============================================================
(() => {
  const UNIT_CATEGORIES = {
    longitud: {
      base: "m",
      units: {
        mm: { label: "Milímetros (mm)", factor: 0.001 },
        cm: { label: "Centímetros (cm)", factor: 0.01 },
        m: { label: "Metros (m)", factor: 1 },
        km: { label: "Kilómetros (km)", factor: 1000 },
        in: { label: "Pulgadas (in)", factor: 0.0254 },
        ft: { label: "Pies (ft)", factor: 0.3048 },
        yd: { label: "Yardas (yd)", factor: 0.9144 },
        mi: { label: "Millas (mi)", factor: 1609.344 },
      },
    },
    peso: {
      base: "kg",
      units: {
        mg: { label: "Miligramos (mg)", factor: 0.000001 },
        g: { label: "Gramos (g)", factor: 0.001 },
        kg: { label: "Kilogramos (kg)", factor: 1 },
        ton: { label: "Toneladas (t)", factor: 1000 },
        oz: { label: "Onzas (oz)", factor: 0.0283495 },
        lb: { label: "Libras (lb)", factor: 0.453592 },
      },
    },
    volumen: {
      base: "l",
      units: {
        ml: { label: "Mililitros (ml)", factor: 0.001 },
        l: { label: "Litros (l)", factor: 1 },
        m3: { label: "Metros cúbicos (m³)", factor: 1000 },
        gal: { label: "Galones US (gal)", factor: 3.78541 },
        qt: { label: "Cuartos US (qt)", factor: 0.946353 },
        floz: { label: "Onzas líquidas US (fl oz)", factor: 0.0295735 },
      },
    },
    temperatura: {
      special: true,
      units: {
        c: { label: "Celsius (°C)" },
        f: { label: "Fahrenheit (°F)" },
        k: { label: "Kelvin (K)" },
      },
    },
  };

  function toCelsius(value, unit) {
    if (unit === "c") return value;
    if (unit === "f") return ((value - 32) * 5) / 9;
    return value - 273.15; // kelvin
  }
  function fromCelsius(celsius, unit) {
    if (unit === "c") return celsius;
    if (unit === "f") return (celsius * 9) / 5 + 32;
    return celsius + 273.15; // kelvin
  }

  function convertUnit(value, category, fromUnit, toUnit) {
    const def = UNIT_CATEGORIES[category];
    if (def.special) {
      return fromCelsius(toCelsius(value, fromUnit), toUnit);
    }
    const baseValue = value * def.units[fromUnit].factor;
    return baseValue / def.units[toUnit].factor;
  }

  const categorySelect = document.getElementById("units-category");
  const inputValue = document.getElementById("units-input-value");
  const inputUnit = document.getElementById("units-input-unit");
  const outputValue = document.getElementById("units-output-value");
  const outputUnit = document.getElementById("units-output-unit");
  const swapBtn = document.getElementById("units-swap");

  function populateUnitSelects() {
    const def = UNIT_CATEGORIES[categorySelect.value];
    const unitKeys = Object.keys(def.units);
    const optionsHtml = unitKeys.map((key) => `<option value="${key}">${def.units[key].label}</option>`).join("");
    inputUnit.innerHTML = optionsHtml;
    outputUnit.innerHTML = optionsHtml;
    inputUnit.value = unitKeys[0];
    outputUnit.value = unitKeys[1] || unitKeys[0];
  }

  function recalculate() {
    const value = Number(inputValue.value);
    if (Number.isNaN(value)) {
      outputValue.value = "";
      return;
    }
    const result = convertUnit(value, categorySelect.value, inputUnit.value, outputUnit.value);
    outputValue.value = Number(result.toFixed(6)).toString();
  }

  categorySelect.addEventListener("change", () => {
    populateUnitSelects();
    recalculate();
  });
  [inputValue, inputUnit, outputUnit].forEach((el) => el.addEventListener("input", recalculate));

  swapBtn.addEventListener("click", () => {
    const tmp = inputUnit.value;
    inputUnit.value = outputUnit.value;
    outputUnit.value = tmp;
    recalculate();
  });

  populateUnitSelects();
  recalculate();
})();

// ============================================================
// Herramienta 8: Convertidor de zona horaria
// ============================================================
(() => {
  const TIME_ZONES = [
    "America/Los_Angeles", "America/Denver", "America/Chicago", "America/New_York",
    "America/Mexico_City", "America/Bogota", "America/Lima", "America/Santiago",
    "America/Argentina/Buenos_Aires", "America/Sao_Paulo",
    "UTC",
    "Europe/London", "Europe/Madrid", "Europe/Paris", "Europe/Berlin", "Europe/Rome", "Europe/Moscow",
    "Africa/Cairo", "Africa/Johannesburg",
    "Asia/Dubai", "Asia/Karachi", "Asia/Kolkata", "Asia/Dhaka", "Asia/Bangkok",
    "Asia/Shanghai", "Asia/Tokyo", "Asia/Seoul", "Asia/Singapore",
    "Australia/Sydney", "Pacific/Auckland",
  ];

  const dateInput = document.getElementById("time-input");
  const fromZoneSelect = document.getElementById("time-from-zone");
  const toZoneSelect = document.getElementById("time-to-zone");
  const resultEl = document.getElementById("time-result");

  function nowAsLocalInputValue() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  function populateZoneSelect(select) {
    select.innerHTML = TIME_ZONES.map((tz) => `<option value="${tz}">${tz.replace(/_/g, " ")}</option>`).join("");
  }

  // Convierte una fecha/hora "naive" (sin zona) interpretada en `timeZone`
  // al instante UTC real, usando solo la API Intl (sin librerías externas).
  function zonedTimeToUtc(localValue, timeZone) {
    const [datePart, timePart] = localValue.split("T");
    const [y, mo, d] = datePart.split("-").map(Number);
    const [h, mi] = timePart.split(":").map(Number);
    const guess = Date.UTC(y, mo - 1, d, h, mi, 0);

    const dtf = new Intl.DateTimeFormat("en-US", {
      timeZone,
      hour12: false,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
    const parts = {};
    dtf.formatToParts(new Date(guess)).forEach((p) => (parts[p.type] = p.value));
    const hour = Number(parts.hour) === 24 ? 0 : Number(parts.hour);
    const asIfUtcAgain = Date.UTC(
      Number(parts.year), Number(parts.month) - 1, Number(parts.day),
      hour, Number(parts.minute), Number(parts.second)
    );
    return guess - (asIfUtcAgain - guess);
  }

  function formatInZone(utcMillis, timeZone) {
    return new Intl.DateTimeFormat("es-AR", {
      timeZone,
      dateStyle: "full",
      timeStyle: "short",
    }).format(new Date(utcMillis));
  }

  function recalculate() {
    if (!dateInput.value) {
      resultEl.textContent = "";
      return;
    }
    const utcMillis = zonedTimeToUtc(dateInput.value, fromZoneSelect.value);
    resultEl.textContent = formatInZone(utcMillis, toZoneSelect.value);
  }

  populateZoneSelect(fromZoneSelect);
  populateZoneSelect(toZoneSelect);
  dateInput.value = nowAsLocalInputValue();

  const detectedZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  if (TIME_ZONES.includes(detectedZone)) {
    fromZoneSelect.value = detectedZone;
  }
  toZoneSelect.value = TIME_ZONES.find((tz) => tz !== fromZoneSelect.value) || TIME_ZONES[0];

  [dateInput, fromZoneSelect, toZoneSelect].forEach((el) => el.addEventListener("input", recalculate));
  recalculate();
})();
