const fs = require('fs');
const PptxGenJS = require('pptxgenjs');

function hex(value) { return String(value || '').replace('#', ''); }
function safeText(value, fallback = '') { return String(value ?? fallback).trim(); }

function addText(slide, text, x, y, w, h, opts = {}) {
  slide.addText(safeText(text), {
    x, y, w, h,
    fontFace: opts.fontFace || 'Aptos',
    fontSize: opts.fontSize || 18,
    bold: !!opts.bold,
    color: hex(opts.color || '171717'),
    margin: opts.margin ?? 0,
    breakLine: false,
    fit: 'shrink',
    valign: opts.valign || 'mid',
    align: opts.align || 'left',
    paraSpaceAfterPt: opts.paraSpaceAfterPt || 0,
    bullet: opts.bullet,
  });
}

function addCard(slide, x, y, w, h, fill, radius = 0.14, line = fill) {
  slide.addShape(PptxGenJS.ShapeType.roundRect, {
    x, y, w, h,
    rectRadius: radius,
    fill: { color: hex(fill) },
    line: { color: hex(line), transparency: 100 },
  });
}

function render(input, output) {
  const theme = input.theme || { bg: 'F7F7F5', ink: '171717', muted: '666666', accent: '111827', soft: 'E5E7EB' };
  const onboarding = input.onboarding || {};
  const slides = Array.isArray(input.slides) ? input.slides : [];
  const company = safeText(onboarding.company_name, 'Company');
  const imagePath = input.image_path && fs.existsSync(input.image_path) ? input.image_path : null;

  const pptx = new PptxGenJS();
  pptx.layout = 'LAYOUT_WIDE';
  pptx.author = 'Pixel Pulse Studio';
  pptx.company = 'Pixel Pulse Studio';
  pptx.subject = safeText(onboarding.service, 'Professional presentation');
  pptx.title = company;
  pptx.lang = 'en-US';
  pptx.theme = {
    headFontFace: 'Aptos Display',
    bodyFontFace: 'Aptos',
    lang: 'en-US'
  };
  pptx.defineSlideMaster({
    title: 'PPS_MASTER',
    background: { color: hex(theme.bg) },
    objects: [
      { rect: { x: 0, y: 0, w: 13.333, h: 0.10, fill: { color: hex(theme.accent) }, line: { color: hex(theme.accent) } } },
      { text: { text: 'PIXEL PULSE STUDIO', options: { x: 0.70, y: 7.08, w: 2.5, h: 0.18, fontFace: 'Aptos', fontSize: 6.5, color: hex(theme.muted), margin: 0 } } }
    ],
    slideNumber: { x: 12.35, y: 7.05, color: hex(theme.muted), fontFace: 'Aptos', fontSize: 7 }
  });

  slides.forEach((item, index) => {
    const slide = pptx.addSlide('PPS_MASTER');
    const layout = safeText(item.layout, 'CONTENT').toUpperCase();
    const title = safeText(item.title, `Slide ${index + 1}`);
    const bullets = (Array.isArray(item.bullets) ? item.bullets : []).map(safeText).filter(Boolean).slice(0, 5);
    const n = index + 1;

    slide.background = { color: hex(theme.bg) };

    if (layout === 'TITLE' || n === 1) {
      slide.background = { color: hex(theme.accent) };
      if (imagePath) {
        slide.addImage({ path: imagePath, x: 8.10, y: 0, w: 5.233, h: 7.50, transparency: 8 });
        slide.addShape(PptxGenJS.ShapeType.rect, { x: 7.55, y: 0, w: 0.72, h: 7.50, fill: { color: hex(theme.accent), transparency: 18 }, line: { color: hex(theme.accent), transparency: 100 } });
      }
      addText(slide, company, 0.78, 0.92, 6.65, 0.72, { fontSize: 28, bold: true, color: 'FFFFFF' });
      addText(slide, title, 0.80, 2.00, 6.25, 1.55, { fontSize: 25, bold: true, color: 'FFFFFF', valign: 'top' });
      if (bullets[0]) addText(slide, bullets[0], 0.82, 5.55, 5.95, 0.72, { fontSize: 15, color: 'E9E9E9', valign: 'top' });
      addText(slide, 'Professional presentation', 0.82, 6.52, 4.5, 0.25, { fontSize: 8.5, color: 'D5D5D5' });
      return;
    }

    addText(slide, title, 0.72, 0.45, 9.9, 0.55, { fontSize: 24, bold: true, color: theme.ink });
    addText(slide, `${company}  •  ${String(n).padStart(2, '0')}/${String(slides.length).padStart(2, '0')}`, 0.74, 1.08, 5.0, 0.24, { fontSize: 8.5, color: theme.muted });

    if (layout === 'SECTION') {
      addCard(slide, 0.75, 1.75, 11.85, 3.95, theme.soft, 0.18);
      addText(slide, title, 1.15, 2.30, 9.8, 0.75, { fontSize: 28, bold: true, color: theme.accent });
      if (bullets[0]) addText(slide, bullets[0], 1.18, 3.20, 9.55, 1.35, { fontSize: 18, color: theme.ink, valign: 'top' });
    } else {
      const hasImage = !!imagePath && [3, 6, 9].includes(n);
      const textW = hasImage ? 7.25 : 11.25;
      if (hasImage) {
        slide.addImage({ path: imagePath, x: 8.55, y: 1.55, w: 4.05, h: 4.72, transparency: 0 });
        addText(slide, 'Visual source: Wikimedia Commons', 8.62, 6.40, 3.75, 0.22, { fontSize: 6.5, color: theme.muted });
      }
      if (bullets.length) {
        const bulletRows = bullets.map(text => ({ text, options: { bullet: { indent: 16 }, hanging: 3, breakLine: true } }));
        slide.addText(bulletRows, {
          x: 0.78, y: 1.65, w: textW, h: 4.70,
          fontFace: 'Aptos', fontSize: bullets.length <= 3 ? 18 : 15.5,
          color: hex(theme.ink), margin: 0.02, breakLine: false,
          valign: 'top', paraSpaceAfterPt: 12, fit: 'shrink'
        });
      }
      addCard(slide, 0.78, 6.55, 1.12, 0.08, theme.accent, 0.02);
      addCard(slide, 2.02, 6.55, 0.34, 0.08, theme.soft, 0.02);
    }
  });

  return pptx.writeFile({ fileName: output });
}

(async () => {
  try {
    const inputPath = process.argv[2];
    const outputPath = process.argv[3];
    if (!inputPath || !outputPath) throw new Error('Usage: node pptxgen_renderer.js INPUT_JSON OUTPUT_PPTX');
    const input = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
    await render(input, outputPath);
    process.stdout.write(JSON.stringify({ ok: true, output: outputPath }));
  } catch (err) {
    process.stderr.write(String(err && err.stack ? err.stack : err));
    process.exit(1);
  }
})();
