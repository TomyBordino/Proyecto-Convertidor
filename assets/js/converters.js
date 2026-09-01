/*
 * Funciones puras de conversión. No tocan el DOM: reciben archivos/opciones
 * y devuelven Blobs (o listas de Blobs) via Promise.
 */

const Converters = (() => {

  const EXT_BY_MIME = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
  };

  function loadImage(file) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => resolve({ img, url });
      img.onerror = () => {
        URL.revokeObjectURL(url);
        reject(new Error("No se pudo leer la imagen: " + file.name));
      };
      img.src = url;
    });
  }

  /**
   * Convierte una imagen a otro formato usando canvas.
   * @param {File} file
   * @param {string} mimeType image/png | image/jpeg | image/webp
   * @param {number} quality 0..1 (solo aplica a jpeg/webp)
   */
  async function convertImage(file, mimeType, quality = 0.9) {
    const { img, url } = await loadImage(file);
    try {
      const canvas = document.createElement("canvas");
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      const ctx = canvas.getContext("2d");

      // JPG no soporta transparencia: pintamos fondo blanco primero.
      if (mimeType === "image/jpeg") {
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
      }
      ctx.drawImage(img, 0, 0);

      const blob = await new Promise((resolve, reject) => {
        canvas.toBlob(
          (b) => (b ? resolve(b) : reject(new Error("Conversión fallida"))),
          mimeType,
          quality
        );
      });

      const baseName = file.name.replace(/\.[^.]+$/, "");
      const outName = `${baseName}.${EXT_BY_MIME[mimeType] || "png"}`;
      return { blob, name: outName };
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  /**
   * Combina varias imágenes en un único PDF.
   * @param {File[]} files
   * @param {{pageSize: 'a4'|'letter'|'fit', orientation: 'p'|'l'}} opts
   */
  async function imagesToPdf(files, opts) {
    const { jsPDF } = window.jspdf;
    let doc = null;

    for (const file of files) {
      const { img, url } = await loadImage(file);
      try {
        const canvas = document.createElement("canvas");
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0);
        const dataUrl = canvas.toDataURL("image/jpeg", 0.92);

        const imgW = img.naturalWidth;
        const imgH = img.naturalHeight;

        if (opts.pageSize === "fit") {
          const unit = "px";
          const format = [imgW, imgH];
          if (!doc) {
            doc = new jsPDF({ orientation: opts.orientation, unit, format });
          } else {
            doc.addPage(format, opts.orientation);
          }
          doc.addImage(dataUrl, "JPEG", 0, 0, imgW, imgH);
        } else {
          if (!doc) {
            doc = new jsPDF({ orientation: opts.orientation, unit: "mm", format: opts.pageSize });
          } else {
            doc.addPage(opts.pageSize, opts.orientation);
          }
          const pageW = doc.internal.pageSize.getWidth();
          const pageH = doc.internal.pageSize.getHeight();
          const scale = Math.min(pageW / imgW, pageH / imgH);
          const w = imgW * scale;
          const h = imgH * scale;
          const x = (pageW - w) / 2;
          const y = (pageH - h) / 2;
          doc.addImage(dataUrl, "JPEG", x, y, w, h);
        }
      } finally {
        URL.revokeObjectURL(url);
      }
    }

    const blob = doc.output("blob");
    return { blob, name: "documento.pdf" };
  }

  /**
   * Renderiza cada página de un PDF como imagen.
   * @param {File} file
   * @param {string} mimeType image/png | image/jpeg
   * @param {number} scale factor de escala de render (nitidez)
   */
  async function pdfToImages(file, mimeType, scale = 2) {
    if (window.pdfjsLib && !window.pdfjsLib.GlobalWorkerOptions.workerSrc) {
      window.pdfjsLib.GlobalWorkerOptions.workerSrc =
        "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
    }

    const arrayBuffer = await file.arrayBuffer();
    const pdf = await window.pdfjsLib.getDocument({ data: arrayBuffer }).promise;
    const baseName = file.name.replace(/\.[^.]+$/, "");
    const ext = EXT_BY_MIME[mimeType] || "png";
    const results = [];

    for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
      const page = await pdf.getPage(pageNum);
      const viewport = page.getViewport({ scale });
      const canvas = document.createElement("canvas");
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      const ctx = canvas.getContext("2d");

      if (mimeType === "image/jpeg") {
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
      }

      await page.render({ canvasContext: ctx, viewport }).promise;

      const blob = await new Promise((resolve, reject) => {
        canvas.toBlob(
          (b) => (b ? resolve(b) : reject(new Error("Render fallido"))),
          mimeType,
          0.92
        );
      });

      const suffix = pdf.numPages > 1 ? `-pagina-${pageNum}` : "";
      results.push({ blob, name: `${baseName}${suffix}.${ext}` });
    }

    return results;
  }

  async function zipFiles(items, zipName) {
    const zip = new JSZip();
    for (const item of items) {
      zip.file(item.name, item.blob);
    }
    const blob = await zip.generateAsync({ type: "blob" });
    return { blob, name: zipName };
  }

  function formatBytes(bytes) {
    if (bytes === 0) return "0 B";
    const units = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
  }

  return { convertImage, imagesToPdf, pdfToImages, zipFiles, formatBytes };
})();
