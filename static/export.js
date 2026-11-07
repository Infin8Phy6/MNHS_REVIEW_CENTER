// MNHSRC - A4 PNG export for answered quizzes.
// Renders the student's answered quiz onto A4 portrait pages (794x1123 px at
// 96 dpi, drawn at 2x for sharpness) and downloads each page as a PNG.
window.RHExport = (function () {
    const A4_W = 794;
    const A4_H = 1123;
    const SCALE = 2;
    const MARGIN = 54;
    const CONTENT_W = A4_W - MARGIN * 2;
    const LINE_H = 19;

    const FONT = "'Segoe UI', Roboto, Helvetica, Arial, sans-serif";
    const C_DARK = '#222222';
    const C_GREY = '#666666';
    const C_LIGHT = '#999999';
    const C_GREEN = '#1e7e34';
    const C_RED = '#c82333';
    const C_BORDER = '#dddddd';

    function wrapText(ctx, text, maxWidth) {
        const words = String(text == null ? '' : text).split(/\s+/).filter(Boolean);
        if (!words.length) return [''];
        const lines = [];
        let line = '';
        words.forEach(function (word) {
            const candidate = line ? line + ' ' + word : word;
            if (ctx.measureText(candidate).width > maxWidth && line) {
                lines.push(line);
                line = word;
            } else {
                line = candidate;
            }
        });
        if (line) lines.push(line);
        return lines;
    }

    function createPage() {
        const canvas = document.createElement('canvas');
        canvas.width = A4_W * SCALE;
        canvas.height = A4_H * SCALE;
        const ctx = canvas.getContext('2d');
        ctx.scale(SCALE, SCALE);
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, A4_W, A4_H);
        return { canvas: canvas, ctx: ctx, y: MARGIN };
    }

    function divider(page) {
        const ctx = page.ctx;
        ctx.strokeStyle = C_BORDER;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(MARGIN, page.y + 6);
        ctx.lineTo(A4_W - MARGIN, page.y + 6);
        ctx.stroke();
        page.y += 18;
    }

    function drawHeader(page, attempt, user) {
        const ctx = page.ctx;
        ctx.textAlign = 'center';
        ctx.fillStyle = C_DARK;
        ctx.font = '800 20px ' + FONT;
        ctx.fillText('REVIEW HUB PH', A4_W / 2, page.y + 10);
        ctx.font = '700 13px ' + FONT;
        ctx.fillStyle = C_GREY;
        ctx.fillText('Answered Quiz Report', A4_W / 2, page.y + 30);
        page.y += 44;
        divider(page);
        ctx.textAlign = 'left';

        const info = user || {};
        const pct = attempt.total ? Math.round((attempt.score / attempt.total) * 100) : 0;
        const rows = [
            ['Name', info.name || '—'],
            ['School', info.school || '—'],
            ['Grade / Section', (info.grade || '—') + ' / ' + (info.section || '—')],
            ['Subject', attempt.subject || '—'],
            ['Topic', attempt.topic || 'All Topics'],
            ['Date Taken', formatDate(attempt.date_taken)],
            ['Score', attempt.score + ' / ' + attempt.total + '  (' + pct + '%)'],
        ];

        ctx.font = '400 13px ' + FONT;
        rows.forEach(function (row) {
            ctx.fillStyle = C_LIGHT;
            ctx.fillText(row[0], MARGIN, page.y + 4);
            ctx.fillStyle = C_DARK;
            ctx.font = '700 13px ' + FONT;
            const valueLines = wrapText(ctx, row[1], CONTENT_W - 150);
            ctx.fillText(valueLines[0], MARGIN + 150, page.y + 4);
            page.y += LINE_H;
            for (let i = 1; i < valueLines.length; i++) {
                ctx.fillText(valueLines[i], MARGIN + 150, page.y + 4);
                page.y += LINE_H;
            }
            ctx.font = '400 13px ' + FONT;
        });
        page.y += 4;
        divider(page);
    }

    function formatDate(value) {
        if (!value) return '—';
        const d = new Date(value);
        if (isNaN(d.getTime())) return String(value);
        return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) +
            ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    }

    function measureItem(ctx, item, index) {
        ctx.font = '700 13px ' + FONT;
        const qLines = wrapText(ctx, index + '. ' + item.question, CONTENT_W);
        let height = qLines.length * LINE_H + 6;

        const options = Array.isArray(item.options) ? item.options : [];
        ctx.font = '400 12.5px ' + FONT;
        if (options.length) {
            options.forEach(function (opt) {
                height += wrapText(ctx, '• ' + opt, CONTENT_W - 16).length * (LINE_H - 2) + 2;
            });
        } else {
            height += wrapText(ctx, 'Your answer: ' + (item.your_answer || '—'), CONTENT_W - 16).length * (LINE_H - 2) + 2;
            height += wrapText(ctx, 'Correct answer: ' + (item.correct || '—'), CONTENT_W - 16).length * (LINE_H - 2) + 2;
        }
        return height + 16;
    }

    function drawItem(page, item, index) {
        const ctx = page.ctx;
        ctx.textAlign = 'left';
        ctx.font = '700 13px ' + FONT;
        ctx.fillStyle = C_DARK;
        wrapText(ctx, index + '. ' + item.question, CONTENT_W).forEach(function (line) {
            ctx.fillText(line, MARGIN, page.y + 4);
            page.y += LINE_H;
        });
        page.y += 6;

        const options = Array.isArray(item.options) ? item.options : [];
        ctx.font = '400 12.5px ' + FONT;
        if (options.length) {
            options.forEach(function (opt) {
                const isYours = String(opt) === String(item.your_answer);
                const isCorrect = String(opt) === String(item.correct);
                ctx.fillStyle = isCorrect ? C_GREEN : (isYours ? C_RED : C_GREY);
                const marker = isCorrect ? '✓ ' : (isYours && !isCorrect ? '✗ ' : '• ');
                wrapText(ctx, marker + opt, CONTENT_W - 16).forEach(function (line) {
                    ctx.fillText(line, MARGIN + 12, page.y + 3);
                    page.y += LINE_H - 2;
                });
                page.y += 2;
            });
        } else {
            ctx.fillStyle = C_RED;
            wrapText(ctx, 'Your answer: ' + (item.your_answer || '—'), CONTENT_W - 16).forEach(function (line) {
                ctx.fillText(line, MARGIN + 12, page.y + 3);
                page.y += LINE_H - 2;
            });
            ctx.fillStyle = C_GREEN;
            wrapText(ctx, 'Correct answer: ' + (item.correct || '—'), CONTENT_W - 16).forEach(function (line) {
                ctx.fillText(line, MARGIN + 12, page.y + 3);
                page.y += LINE_H - 2;
            });
        }
        page.y += 16;
    }

    function drawFooter(page, pageNum, totalPages, label) {
        const ctx = page.ctx;
        ctx.font = '400 10px ' + FONT;
        ctx.fillStyle = C_LIGHT;
        ctx.textAlign = 'left';
        ctx.fillText(label || 'MNHSRC — Quiz Result', MARGIN, A4_H - 30);
        ctx.textAlign = 'right';
        ctx.fillText('Page ' + pageNum + ' of ' + totalPages, A4_W - MARGIN, A4_H - 30);
        ctx.textAlign = 'left';
    }

    function sanitizeFilename(text) {
        return String(text || 'Quiz').replace(/[^A-Za-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 40) || 'Quiz';
    }

    // A page is built, flattened to PNG and thrown away before the next one is
    // made: keeping every A4 canvas at 2x alive at once is what runs a phone
    // out of memory, and a failed toBlob used to end the export in silence.
    function downloadCanvas(canvas, filename) {
        return new Promise(function (resolve, reject) {
            canvas.toBlob(function (blob) {
                if (!blob) {
                    reject(new Error('png_encode_failed'));
                    return;
                }
                const url = URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = url;
                link.download = filename;
                document.body.appendChild(link);
                link.click();
                link.remove();
                setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
                canvas.width = 1;
                canvas.height = 1;
                setTimeout(resolve, 600);
            }, 'image/png');
        });
    }

    // Work out where each page starts and ends before drawing anything, so the
    // footers can say "Page n of N" while pages are still rendered one by one.
    function planPages(ctx, startY, items, measure) {
        const needed_of = measure || measureItem;
        const pages = [{ start: 0 }];
        let y = startY;
        items.forEach(function (item, i) {
            const needed = needed_of(ctx, item, i + 1);
            if (y + needed > A4_H - 60) {
                pages[pages.length - 1].end = i;
                pages.push({ start: i });
                y = MARGIN;
            }
            y += needed;
        });
        pages[pages.length - 1].end = items.length;
        return pages;
    }

    // Draws the report page by page and hands each finished canvas to `fn`
    // before the next one is created, so no phone runs out of memory.
    async function eachRenderedPage(attempt, user, fn) {
        const items = Array.isArray(attempt.quiz_set_info) ? attempt.quiz_set_info : [];
        const first = createPage();
        drawHeader(first, attempt, user);
        const plan = items.length
            ? planPages(first.ctx, first.y, items)
            : [{ start: 0, end: 0 }];

        let page = first;
        for (let i = 0; i < plan.length; i++) {
            if (i > 0) page = createPage();
            for (let n = plan[i].start; n < plan[i].end; n++) {
                drawItem(page, items[n], n + 1);
            }
            drawFooter(page, i + 1, plan.length);
            await fn(page.canvas, i + 1, plan.length);
            page.canvas.width = 1;
            page.canvas.height = 1;
        }
        return plan.length;
    }

    function fileName(attempt, ext) {
        return 'ReviewHub_' + sanitizeFilename(attempt.subject) + '_' +
            sanitizeFilename(attempt.date_taken || '') + ext;
    }

    async function exportAttempt(attempt, user) {
        const base = fileName(attempt, '');
        return eachRenderedPage(attempt, user, function (canvas, pageNum) {
            return downloadCanvas(canvas, base + '_page' + pageNum + '.png');
        });
    }

    // One A4 sheet per page, each holding the whole sheet as a single JPEG.
    // Writing the PDF by hand keeps the app working with no internet and no
    // library to fetch.
    function canvasToJpeg(canvas) {
        return new Promise(function (resolve, reject) {
            canvas.toBlob(function (blob) {
                if (!blob) { reject(new Error('jpeg_encode_failed')); return; }
                blob.arrayBuffer().then(resolve, reject);
            }, 'image/jpeg', 0.92);
        });
    }

    function bytesOf(text) {
        const b = new Uint8Array(text.length);
        for (let i = 0; i < text.length; i++) b[i] = text.charCodeAt(i) & 0xff;
        return b;
    }

    function buildPdf(images) {
        const PT_W = 595.28;
        const PT_H = 841.89;
        const count = images.length;
        // Object 1 is the catalog, 2 the page tree, then per page: image, page,
        // page contents.
        const firstPageObj = 3;
        const objects = [];

        objects[1] = '<< /Type /Catalog /Pages 2 0 R >>';
        const kids = [];
        for (let i = 0; i < count; i++) {
            kids.push((firstPageObj + i * 3 + 1) + ' 0 R');
        }
        objects[2] = '<< /Type /Pages /Count ' + count + ' /Kids [' + kids.join(' ') + '] >>';

        for (let i = 0; i < count; i++) {
            const imgObj = firstPageObj + i * 3;
            const pageObj = imgObj + 1;
            const contentObj = imgObj + 2;
            const img = images[i];
            objects[imgObj] = {
                header: '<< /Type /XObject /Subtype /Image /Width ' + img.width + ' /Height ' + img.height +
                    ' /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ' +
                    img.bytes.length + ' >>',
                stream: img.bytes,
            };
            objects[pageObj] = '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ' + PT_W + ' ' + PT_H + '] ' +
                '/Resources << /XObject << /Im0 ' + imgObj + ' 0 R >> >> /Contents ' + contentObj + ' 0 R >>';
            // A content stream needs its own /Length and stream markers; a bare
            // command string is not a PDF object a reader will accept.
            const commands = bytesOf('q ' + PT_W + ' 0 0 ' + PT_H + ' 0 0 cm /Im0 Do Q');
            objects[contentObj] = {
                header: '<< /Length ' + commands.length + ' >>',
                stream: commands,
            };
        }

        const chunks = [];
        let offset = 0;
        function push(data) {
            const bytes = typeof data === 'string' ? bytesOf(data) : data;
            chunks.push(bytes);
            offset += bytes.length;
        }

        push('%PDF-1.4\n');
        // Marks the file as binary so a reader does not choke on the JPEG bytes.
        push('%\u00E2\u00E3\u00CF\u00D3\n');
        const offsets = [];
        for (let n = 1; n < objects.length; n++) {
            offsets[n] = offset;
            const obj = objects[n];
            if (obj == null || obj === '') continue;
            if (typeof obj === 'object') {
                push(n + ' 0 obj\n' + obj.header + '\nstream\n');
                push(obj.stream);
                push('\nendstream\nendobj\n');
            } else {
                push(n + ' 0 obj\n' + obj + '\nendobj\n');
            }
        }

        const xrefAt = offset;
        let xref = 'xref\n0 ' + objects.length + '\n0000000000 65535 f \n';
        for (let n = 1; n < objects.length; n++) {
            xref += String(offsets[n] || 0).padStart(10, '0') + ' 00000 n \n';
        }
        push(xref);
        push('trailer\n<< /Size ' + objects.length + ' /Root 1 0 R >>\nstartxref\n' +
            xrefAt + '\n%%EOF\n');

        const pdf = new Uint8Array(offset);
        let at = 0;
        chunks.forEach(function (c) { pdf.set(c, at); at += c.length; });
        return pdf;
    }

    async function exportPdf(attempt, user) {
        const images = [];
        const pages = await eachRenderedPage(attempt, user, async function (canvas) {
            const buffer = await canvasToJpeg(canvas);
            images.push({ bytes: new Uint8Array(buffer), width: canvas.width, height: canvas.height });
        });
        if (!pages) throw new Error('nothing_to_export');
        saveBytes(buildPdf(images), 'application/pdf', fileName(attempt, '.pdf'));
        return pages;
    }

    // --- Summative test paper: questions and choices only, no answers shown ---
    const LETTERS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J'];

    function drawTestHeader(page, meta) {
        const ctx = page.ctx;
        const info = meta || {};
        ctx.textAlign = 'center';
        ctx.fillStyle = C_DARK;
        ctx.font = '800 20px ' + FONT;
        ctx.fillText('REVIEW HUB PH', A4_W / 2, page.y + 10);
        ctx.font = '700 15px ' + FONT;
        const titleLines = wrapText(ctx, info.title || 'Summative Test', CONTENT_W);
        titleLines.forEach(function (line, i) {
            ctx.fillText(line, A4_W / 2, page.y + 32 + i * LINE_H);
        });
        ctx.font = '400 12px ' + FONT;
        ctx.fillStyle = C_GREY;
        const scope = [info.level, info.subject].filter(Boolean).join(' — ');
        if (scope) ctx.fillText(scope, A4_W / 2, page.y + 32 + titleLines.length * LINE_H);
        page.y += 34 + titleLines.length * LINE_H + (scope ? LINE_H : 0);
        divider(page);

        ctx.textAlign = 'left';
        ctx.fillStyle = C_DARK;
        ctx.font = '400 13px ' + FONT;
        ctx.fillText('Name: ____________________________  Section: __________  Date: __________',
            MARGIN, page.y + 4);
        page.y += LINE_H + 4;
        ctx.fillText('Score: ________ / ' + (info.total || 0), MARGIN, page.y + 4);
        page.y += LINE_H + 6;

        if (info.topics) {
            ctx.fillStyle = C_GREY;
            ctx.font = '400 11.5px ' + FONT;
            wrapText(ctx, 'Covering: ' + info.topics, CONTENT_W).forEach(function (line) {
                ctx.fillText(line, MARGIN, page.y + 3);
                page.y += LINE_H - 3;
            });
            page.y += 4;
        }

        ctx.fillStyle = C_DARK;
        ctx.font = '400 12px ' + FONT;
        wrapText(ctx, 'Directions: Read each item carefully. Write the letter of the best answer ' +
            'on the space before the number.', CONTENT_W).forEach(function (line) {
            ctx.fillText(line, MARGIN, page.y + 3);
            page.y += LINE_H - 2;
        });
        page.y += 8;
        divider(page);
    }

    function measureTestItem(ctx, item, index) {
        ctx.font = '700 13px ' + FONT;
        let height = wrapText(ctx, index + '. ______ ' + item.question, CONTENT_W).length * LINE_H + 8;
        ctx.font = '400 12.5px ' + FONT;
        testOptions(item).forEach(function (opt, i) {
            height += wrapText(ctx, optionText(opt, i), CONTENT_W - 34).length * (LINE_H - 2) + 2;
        });
        return height + 14;
    }

    function drawTestItem(page, item, index) {
        const ctx = page.ctx;
        ctx.textAlign = 'left';
        ctx.font = '700 13px ' + FONT;
        ctx.fillStyle = C_DARK;
        wrapText(ctx, index + '. ______ ' + item.question, CONTENT_W).forEach(function (line) {
            ctx.fillText(line, MARGIN, page.y + 4);
            page.y += LINE_H;
        });
        page.y += 8;

        ctx.font = '400 12.5px ' + FONT;
        ctx.fillStyle = C_GREY;
        testOptions(item).forEach(function (opt, i) {
            wrapText(ctx, optionText(opt, i), CONTENT_W - 34).forEach(function (line, n) {
                ctx.fillText(line, MARGIN + (n ? 22 : 34), page.y + 3);
                page.y += LINE_H - 2;
            });
            page.y += 2;
        });
        page.y += 14;
    }

    function testOptions(item) {
        return Array.isArray(item.options) ? item.options : [];
    }

    function optionText(option, index) {
        const letter = LETTERS[index] ? LETTERS[index] + '.' : (index + 1) + '.';
        return letter + ' ' + option;
    }

    async function eachTestPage(meta, items, fn) {
        const first = createPage();
        drawTestHeader(first, meta);
        const plan = items.length
            ? planPages(first.ctx, first.y, items, measureTestItem)
            : [{ start: 0, end: 0 }];

        let page = first;
        for (let i = 0; i < plan.length; i++) {
            if (i > 0) page = createPage();
            for (let n = plan[i].start; n < plan[i].end; n++) {
                drawTestItem(page, items[n], n + 1);
            }
            drawFooter(page, i + 1, plan.length, 'MNHSRC — Summative Test');
            await fn(page.canvas, i + 1, plan.length);
            page.canvas.width = 1;
            page.canvas.height = 1;
        }
        return plan.length;
    }

    function testFileName(meta) {
        return 'SummativeTest_' + sanitizeFilename((meta && meta.title) || 'Summative_Test') + '_' +
            sanitizeFilename((meta && meta.subject) || '') + '.pdf';
    }

    async function exportTest(meta, items) {
        const list = Array.isArray(items) ? items : [];
        if (!list.length) throw new Error('nothing_to_export');
        const info = Object.assign({ total: list.length }, meta || {});
        const images = [];
        await eachTestPage(info, list, async function (canvas) {
            const buffer = await canvasToJpeg(canvas);
            images.push({ bytes: new Uint8Array(buffer), width: canvas.width, height: canvas.height });
        });
        saveBytes(buildPdf(images), 'application/pdf', testFileName(info));
        return images.length;
    }

    function saveBytes(bytes, mime, filename) {
        const url = URL.createObjectURL(new Blob([bytes], { type: mime }));
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
    }

    return { exportAttempt: exportAttempt, exportPdf: exportPdf, exportTest: exportTest };
})();
