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
  function ensurePdfWorker() {
    if (window.pdfjsLib && !window.pdfjsLib.GlobalWorkerOptions.workerSrc) {
      window.pdfjsLib.GlobalWorkerOptions.workerSrc =
        "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
    }
  }

  async function pdfToImages(file, mimeType, scale = 2) {
    ensurePdfWorker();

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

  /**
   * Comprime una imagen re-codificándola con pérdida y, opcionalmente,
   * reduciendo sus dimensiones. Los JPG se mantienen como JPG; el resto
   * (PNG, GIF, etc.) se exporta como WEBP, que comprime mucho mejor y
   * conserva la transparencia.
   * @param {File} file
   * @param {{quality: number, maxWidth: number}} opts quality 0..1, maxWidth en px (0 = sin límite)
   */
  async function compressImage(file, opts) {
    const { img, url } = await loadImage(file);
    try {
      let targetW = img.naturalWidth;
      let targetH = img.naturalHeight;
      if (opts.maxWidth && targetW > opts.maxWidth) {
        const scale = opts.maxWidth / targetW;
        targetW = Math.round(targetW * scale);
        targetH = Math.round(targetH * scale);
      }

      const canvas = document.createElement("canvas");
      canvas.width = targetW;
      canvas.height = targetH;
      const ctx = canvas.getContext("2d");

      const outputMime = file.type === "image/jpeg" ? "image/jpeg" : "image/webp";
      if (outputMime === "image/jpeg") {
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
      }
      ctx.drawImage(img, 0, 0, targetW, targetH);

      const blob = await new Promise((resolve, reject) => {
        canvas.toBlob(
          (b) => (b ? resolve(b) : reject(new Error("Compresión fallida"))),
          outputMime,
          opts.quality
        );
      });

      const baseName = file.name.replace(/\.[^.]+$/, "");
      const ext = outputMime === "image/jpeg" ? "jpg" : "webp";
      return { blob, name: `${baseName}-comprimido.${ext}`, originalSize: file.size };
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  // ============================================================
  // Fuentes: TTF/OTF ⇄ WOFF (formato "contenedor", sin tocar los
  // contornos de la tipografía; WOFF2 no está soportado)
  // ============================================================

  const SIG_WOFF = 0x774f4646; // 'wOFF'
  const SIG_WOFF2 = 0x774f4632; // 'wOF2'
  const SIG_TRUETYPE = 0x00010000;
  const SIG_OTTO = 0x4f54544f; // 'OTTO'
  const SIG_TRUE = 0x74727565; // 'true' (mac TrueType)

  function sfntToWoff(buffer) {
    const view = new DataView(buffer);
    const flavor = view.getUint32(0);
    const numTables = view.getUint16(4);

    const tables = [];
    let offset = 12;
    for (let i = 0; i < numTables; i++) {
      tables.push({
        tag: new Uint8Array(buffer.slice(offset, offset + 4)),
        checksum: view.getUint32(offset + 4),
        tableOffset: view.getUint32(offset + 8),
        length: view.getUint32(offset + 12),
      });
      offset += 16;
    }

    const totalSfntSize = tables.reduce(
      (sum, t) => sum + Math.ceil(t.length / 4) * 4,
      12 + 16 * numTables
    );

    const compressedTables = tables.map((t) => {
      const original = new Uint8Array(buffer, t.tableOffset, t.length);
      const compressed = pako.deflate(original);
      const useCompressed = compressed.length < original.length;
      return {
        tag: t.tag,
        checksum: t.checksum,
        origLength: t.length,
        data: useCompressed ? compressed : original,
        compLength: useCompressed ? compressed.length : t.length,
      };
    });

    let dataOffset = 44 + 20 * numTables;
    const dirEntries = [];
    const dataChunks = [];
    for (const t of compressedTables) {
      dirEntries.push({ ...t, offset: dataOffset });
      const padded = Math.ceil(t.compLength / 4) * 4;
      const chunk = new Uint8Array(padded);
      chunk.set(t.data);
      dataChunks.push(chunk);
      dataOffset += padded;
    }

    const out = new Uint8Array(dataOffset);
    const outView = new DataView(out.buffer);
    outView.setUint32(0, SIG_WOFF);
    outView.setUint32(4, flavor);
    outView.setUint32(8, dataOffset);
    outView.setUint16(12, numTables);
    outView.setUint16(14, 0);
    outView.setUint32(16, totalSfntSize);
    outView.setUint16(20, 0);
    outView.setUint16(22, 0);
    outView.setUint32(24, 0);
    outView.setUint32(28, 0);
    outView.setUint32(32, 0);
    outView.setUint32(36, 0);
    outView.setUint32(40, 0);

    let pos = 44;
    for (const e of dirEntries) {
      out.set(e.tag, pos);
      outView.setUint32(pos + 4, e.offset);
      outView.setUint32(pos + 8, e.compLength);
      outView.setUint32(pos + 12, e.origLength);
      outView.setUint32(pos + 16, e.checksum);
      pos += 20;
    }
    for (const chunk of dataChunks) {
      out.set(chunk, pos);
      pos += chunk.length;
    }

    return out.buffer;
  }

  function woffToSfnt(buffer) {
    const view = new DataView(buffer);
    const flavor = view.getUint32(4);
    const numTables = view.getUint16(12);

    const entries = [];
    let offset = 44;
    for (let i = 0; i < numTables; i++) {
      entries.push({
        tag: new Uint8Array(buffer.slice(offset, offset + 4)),
        tableOffset: view.getUint32(offset + 4),
        compLength: view.getUint32(offset + 8),
        origLength: view.getUint32(offset + 12),
        checksum: view.getUint32(offset + 16),
      });
      offset += 20;
    }

    const tablesData = entries.map((e) => {
      const raw = new Uint8Array(buffer, e.tableOffset, e.compLength);
      const data = e.compLength === e.origLength ? raw : pako.inflate(raw);
      return { tag: e.tag, checksum: e.checksum, data };
    });

    let entrySelector = 0;
    while (1 << (entrySelector + 1) <= numTables) entrySelector++;
    const searchRange = (1 << entrySelector) * 16;
    const rangeShift = numTables * 16 - searchRange;

    let dataOffset = 12 + 16 * numTables;
    const dirEntries = [];
    const dataChunks = [];
    for (const t of tablesData) {
      dirEntries.push({ tag: t.tag, checksum: t.checksum, offset: dataOffset, length: t.data.length });
      const padded = Math.ceil(t.data.length / 4) * 4;
      const chunk = new Uint8Array(padded);
      chunk.set(t.data);
      dataChunks.push(chunk);
      dataOffset += padded;
    }

    const out = new Uint8Array(dataOffset);
    const outView = new DataView(out.buffer);
    outView.setUint32(0, flavor);
    outView.setUint16(4, numTables);
    outView.setUint16(6, searchRange);
    outView.setUint16(8, entrySelector);
    outView.setUint16(10, rangeShift);

    let pos = 12;
    for (const e of dirEntries) {
      out.set(e.tag, pos);
      outView.setUint32(pos + 4, e.checksum);
      outView.setUint32(pos + 8, e.offset);
      outView.setUint32(pos + 12, e.length);
      pos += 16;
    }
    for (const chunk of dataChunks) {
      out.set(chunk, pos);
      pos += chunk.length;
    }

    const ext = flavor === SIG_OTTO ? "otf" : "ttf";
    return { buffer: out.buffer, ext };
  }

  async function convertFont(file) {
    const buffer = await file.arrayBuffer();
    const sig = new DataView(buffer).getUint32(0);
    const baseName = file.name.replace(/\.[^.]+$/, "");

    if (sig === SIG_WOFF) {
      const { buffer: sfntBuf, ext } = woffToSfnt(buffer);
      return { blob: new Blob([sfntBuf]), name: `${baseName}.${ext}` };
    }
    if (sig === SIG_WOFF2) {
      throw new Error("WOFF2 no está soportado por ahora. Probá con un archivo .woff, .ttf o .otf.");
    }
    if (sig === SIG_TRUETYPE || sig === SIG_OTTO || sig === SIG_TRUE) {
      const outBuf = sfntToWoff(buffer);
      return { blob: new Blob([outBuf]), name: `${baseName}.woff` };
    }
    throw new Error("Formato de fuente no reconocido. Subí un archivo .ttf, .otf o .woff.");
  }

  // ============================================================
  // Audio: cualquier formato que el navegador pueda decodificar → WAV o MP3
  // ============================================================

  function audioBufferToWav(audioBuffer) {
    const numChannels = audioBuffer.numberOfChannels;
    const sampleRate = audioBuffer.sampleRate;
    const numFrames = audioBuffer.length;
    const blockAlign = numChannels * 2;
    const dataSize = numFrames * blockAlign;
    const buffer = new ArrayBuffer(44 + dataSize);
    const view = new DataView(buffer);

    const writeString = (offset, str) => {
      for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
    };

    writeString(0, "RIFF");
    view.setUint32(4, 36 + dataSize, true);
    writeString(8, "WAVE");
    writeString(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * blockAlign, true);
    view.setUint16(32, blockAlign, true);
    view.setUint16(34, 16, true);
    writeString(36, "data");
    view.setUint32(40, dataSize, true);

    const channelData = [];
    for (let c = 0; c < numChannels; c++) channelData.push(audioBuffer.getChannelData(c));

    let offset = 44;
    for (let i = 0; i < numFrames; i++) {
      for (let c = 0; c < numChannels; c++) {
        const sample = Math.max(-1, Math.min(1, channelData[c][i]));
        view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
        offset += 2;
      }
    }
    return buffer;
  }

  function floatTo16BitPCM(channelFloat) {
    const out = new Int16Array(channelFloat.length);
    for (let i = 0; i < channelFloat.length; i++) {
      const s = Math.max(-1, Math.min(1, channelFloat[i]));
      out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return out;
  }

  function audioBufferToMp3(audioBuffer, bitrateKbps) {
    const channels = Math.min(audioBuffer.numberOfChannels, 2);
    const encoder = new lamejs.Mp3Encoder(channels, audioBuffer.sampleRate, bitrateKbps);
    const blockSize = 1152;
    const chunks = [];

    const left = floatTo16BitPCM(audioBuffer.getChannelData(0));
    const right = channels === 2 ? floatTo16BitPCM(audioBuffer.getChannelData(1)) : null;

    for (let i = 0; i < left.length; i += blockSize) {
      const leftChunk = left.subarray(i, i + blockSize);
      const buf = right
        ? encoder.encodeBuffer(leftChunk, right.subarray(i, i + blockSize))
        : encoder.encodeBuffer(leftChunk);
      if (buf.length > 0) chunks.push(new Int8Array(buf));
    }
    const finalBuf = encoder.flush();
    if (finalBuf.length > 0) chunks.push(new Int8Array(finalBuf));

    return new Blob(chunks, { type: "audio/mpeg" });
  }

  /**
   * @param {File} file
   * @param {{format: 'wav'|'mp3', bitrate: number}} opts
   */
  async function convertAudio(file, opts) {
    const arrayBuffer = await file.arrayBuffer();
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    const audioCtx = new AudioContextClass();
    let audioBuffer;
    try {
      audioBuffer = await audioCtx.decodeAudioData(arrayBuffer);
    } catch (e) {
      throw new Error("No se pudo leer ese audio. Probá con MP3, WAV, OGG o M4A.");
    } finally {
      audioCtx.close();
    }

    const baseName = file.name.replace(/\.[^.]+$/, "");
    if (opts.format === "mp3") {
      const blob = audioBufferToMp3(audioBuffer, opts.bitrate || 192);
      return { blob, name: `${baseName}.mp3` };
    }
    const blob = new Blob([audioBufferToWav(audioBuffer)], { type: "audio/wav" });
    return { blob, name: `${baseName}.wav` };
  }

  // ============================================================
  // Documentos: TXT/Markdown → PDF, y PDF → TXT
  // ============================================================

  async function textToPdf(file) {
    const text = await file.text();
    const { jsPDF } = window.jspdf;
    const doc = new jsPDF({ unit: "pt", format: "a4" });
    const marginX = 48;
    const marginY = 56;
    const pageWidth = doc.internal.pageSize.getWidth();
    const pageHeight = doc.internal.pageSize.getHeight();
    const lineHeight = 15;

    doc.setFont("helvetica");
    doc.setFontSize(11);
    const lines = doc.splitTextToSize(text, pageWidth - marginX * 2);

    let y = marginY;
    for (const line of lines) {
      if (y > pageHeight - marginY) {
        doc.addPage();
        y = marginY;
      }
      doc.text(line, marginX, y);
      y += lineHeight;
    }

    const baseName = file.name.replace(/\.[^.]+$/, "");
    return { blob: doc.output("blob"), name: `${baseName}.pdf` };
  }

  async function pdfToText(file) {
    ensurePdfWorker();
    const arrayBuffer = await file.arrayBuffer();
    const pdf = await window.pdfjsLib.getDocument({ data: arrayBuffer }).promise;

    let fullText = "";
    for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
      const page = await pdf.getPage(pageNum);
      const content = await page.getTextContent();
      fullText += content.items.map((it) => it.str).join(" ") + "\n\n";
    }

    const baseName = file.name.replace(/\.[^.]+$/, "");
    return { blob: new Blob([fullText], { type: "text/plain" }), name: `${baseName}.txt` };
  }

  async function convertDocument(file) {
    const name = file.name.toLowerCase();
    if (name.endsWith(".pdf") || file.type === "application/pdf") {
      return pdfToText(file);
    }
    if (name.endsWith(".txt") || name.endsWith(".md") || file.type.startsWith("text/")) {
      return textToPdf(file);
    }
    throw new Error("Formato no soportado. Subí un archivo .txt, .md o .pdf.");
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

  return {
    convertImage,
    compressImage,
    imagesToPdf,
    pdfToImages,
    convertFont,
    convertAudio,
    convertDocument,
    zipFiles,
    formatBytes,
  };
})();
