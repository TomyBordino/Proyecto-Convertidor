/* Lógica de interfaz: tabs, dropzones, listas de archivos y disparo de conversiones. */

document.getElementById("year").textContent = new Date().getFullYear();

// ---------- Tabs ----------
const tabButtons = document.querySelectorAll(".tab-btn");
const panels = document.querySelectorAll(".tool-panel");

tabButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    tabButtons.forEach((b) => {
      b.classList.remove("active");
      b.setAttribute("aria-selected", "false");
    });
    btn.classList.add("active");
    btn.setAttribute("aria-selected", "true");

    const targetId = "panel-" + btn.dataset.tab;
    panels.forEach((p) => p.classList.toggle("active", p.id === targetId));
  });
});

// ---------- Helper: dropzone + input genérico ----------
function setupDropzone(dropzoneId, inputId, onFilesSelected) {
  const dropzone = document.getElementById(dropzoneId);
  const input = document.getElementById(inputId);

  const triggerBtn = document.querySelector(`[data-trigger="${inputId}"]`);
  if (triggerBtn) triggerBtn.addEventListener("click", () => input.click());

  dropzone.addEventListener("click", (e) => {
    if (e.target === dropzone || e.target.tagName === "P") input.click();
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
    selectedFiles = files.filter((f) => f.type.startsWith("image/"));
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
    selectedFiles = files.filter((f) => f.type.startsWith("image/"));
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
