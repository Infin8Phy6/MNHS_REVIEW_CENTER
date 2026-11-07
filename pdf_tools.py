"""PDF Studio's jobs, with no window attached.

Every tool the staff page offers is a function here: give it a list of files and
the few choices from the form, and it writes the result into the folder named by
opt['out'], reporting progress through the log callable. The desktop window in
pdf_studio.py draws the same TOOLS list, so the two never drift apart - a fix or
a new tool reaches both copies at once.

Nothing here imports tkinter. The staff page runs inside the Flask app (which may
be on PythonAnywhere), where there is no window to open.
"""
import io
import os
import re

from pypdf import PdfReader, PdfWriter
import pypdf

try:                                    # pypdf needs this for AES locked files
    import cryptography                 # noqa: F401
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

try:                                    # PyMuPDF renamed its import in 2024
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        fitz = None

try:
    from PIL import Image
except ImportError:
    Image = None


PAPERS = {'Image size': None, 'A4': (8.27, 11.69), 'Letter': (8.5, 11.0),
          'Legal': (8.5, 14.0)}
IMAGES = ('.png', '.jpg', '.jpeg', '.jfif', '.bmp', '.tif', '.tiff', '.gif', '.webp')
ALL = 'all'


# --------------------------------------------------------------- small helpers
def human(n):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return ('%d %s' % (n, unit)) if unit == 'B' else ('%.1f %s' % (n, unit))
        n /= 1024.0


def page_sizes_mm(page):
    box = page.mediabox
    return round(float(box.width) * 25.4 / 72), round(float(box.height) * 25.4 / 72)


def paper_name(page):
    w, h = page_sizes_mm(page)
    for label, size in PAPERS.items():
        if size and abs(w - size[0] * 25.4) < 8 and abs(h - size[1] * 25.4) < 8:
            return label
    return '%dx%d mm' % (w, h)


def parse_pages(text, total, repeats=False):
    """'1,3,5-8', 'all', 'even', 'odd', '4-' -> zero based page numbers."""
    text = (text or '').strip().lower()
    if text in ('', ALL, '*'):
        return list(range(total))
    if text in ('even', 'evens'):
        return [i for i in range(total) if i % 2 == 1]      # page 2, 4, 6...
    if text in ('odd', 'odds'):
        return [i for i in range(total) if i % 2 == 0]      # page 1, 3, 5...
    out = []
    for chunk in text.replace(';', ',').split(','):
        chunk = chunk.strip()
        if not chunk:
            continue
        if '-' in chunk:
            head, _, tail = chunk.partition('-')
            start = int(head) if head.strip() else 1
            stop = int(tail) if tail.strip() else total
            rng = range(start, stop + 1) if stop >= start else range(start, stop - 1, -1)
            out.extend(p - 1 for p in rng)
        elif chunk.lstrip('+').isdigit():
            out.append(int(chunk) - 1)
        else:
            raise ValueError("'%s' is not a page number or a range like 3-6." % chunk)
    bad = [p for p in out if p < 0 or p >= total]
    if bad:
        raise ValueError('Page %d is not in a %d-page file.' % (bad[0] + 1, total))
    if not repeats:
        kept = []
        for p in out:
            if p not in kept:
                kept.append(p)
        out = kept
    return out


def reader_of(path, password=None):
    try:
        doc = PdfReader(path)
        if doc.is_encrypted:
            doc.decrypt(password or '')
        return doc
    except Exception as exc:
        if 'cryptography' in str(exc).lower():
            raise RuntimeError('%s is locked with AES. Install the one extra library:\n'
                               '    python -m pip install -r requirements.txt'
                               % os.path.basename(path))
        raise


def pdf_version(path):
    """The '%PDF-1.7' header, since pypdf stopped exposing it."""
    with open(path, 'rb') as f:
        head = f.read(2048)
    found = re.search(rb'%PDF-(\d+\.\d+)', head)
    return found.group(1).decode() if found else '?'


def report(made, verb):
    """One honest closing line: the file when there is one, the folder when there are many."""
    where = made[0] if len(made) == 1 else os.path.dirname(made[0])
    return '%s %d file%s -> %s' % (verb, len(made), '' if len(made) == 1 else 's', where)


def need_fitz(tool):
    if fitz is None:
        raise RuntimeError('%s needs PyMuPDF. Run: python -m pip install -r requirements.txt' % tool)


def stem_of(path):
    return os.path.splitext(os.path.basename(path))[0]


def unique(path):
    """A name that does not clash, so running a job twice keeps both results."""
    if not os.path.exists(path):
        return path
    folder, ext = os.path.dirname(path) or '.', os.path.splitext(path)[1]
    base, n = stem_of(path), 2
    while os.path.exists(os.path.join(folder, '%s (%d)%s' % (base, n, ext))):
        n += 1
    return os.path.join(folder, '%s (%d)%s' % (base, n, ext))


def target(opt, path, suffix, ext='.pdf'):
    """Where a job writes one file: the name you typed (replaced quietly),
    or a fresh one beside the input when you typed nothing."""
    chosen = opt.get('out')
    if chosen and not os.path.isdir(chosen):
        return chosen
    folder = chosen or os.path.dirname(path) or '.'
    return unique(os.path.join(folder, '%s - %s%s' % (stem_of(path), suffix, ext)))


def dest_folder(opt, files, tag):
    """Where a job writes many files, made if it is not there yet."""
    chosen = opt.get('out')
    if chosen and os.path.isdir(chosen):
        folder = chosen
    elif chosen:
        folder = os.path.splitext(chosen)[0]
    else:
        folder = os.path.join(os.path.dirname(files[0]) or '.', '%s - %s' % (stem_of(files[0]), tag))
    os.makedirs(folder, exist_ok=True)
    return folder


def dest(opt, path, suffix, ext='.pdf'):
    """A fresh file for one input, named the same way by every tool. A typed
    "Save as" only supplies the folder here, since these jobs write many files."""
    chosen = opt.get('out')
    if chosen and os.path.isdir(chosen):
        folder = chosen
    elif chosen:
        folder = os.path.dirname(chosen) or '.'
    else:
        folder = os.path.dirname(path) or '.'
    return unique(os.path.join(folder, '%s - %s%s' % (stem_of(path), suffix, ext)))


# ------------------------------------------------------------------------- jobs
def job_merge(files, opt, log):
    if len(files) < 2:
        raise ValueError('Merge wants at least two PDFs in the list.')
    writer = PdfWriter()
    pages = 0
    for path in files:
        doc = reader_of(path, opt.get('password'))
        writer.append(doc)
        pages += len(doc.pages)
        log('  added %d pages from %s' % (len(doc.pages), os.path.basename(path)))
    out = target(opt, files[0], 'merged')
    with open(out, 'wb') as f:
        writer.write(f)
    return 'Merged %d files, %d pages -> %s' % (len(files), pages, out)


def job_split(files, opt, log):
    src = files[0]
    doc = reader_of(src, opt.get('password'))
    total = len(doc.pages)
    mode = opt['mode']
    stem = os.path.splitext(os.path.basename(src))[0]

    if mode == 'One file per page':
        groups = [(i + 1, i, i) for i in range(total)]
    elif mode == 'Every N pages':
        step = max(1, int(opt['value'] or 1))
        groups = [(n, s, min(s + step, total) - 1) for n, s in
                  enumerate(range(0, total, step), 1)]
    else:                                          # cut after these pages
        cuts = sorted(p for p in parse_pages(opt['value'], total) if p < total - 1)
        edges = [-1] + cuts + [total - 1]
        groups = [(n, edges[n - 1] + 1, edges[n]) for n in range(1, len(edges))]

    folder = dest_folder(opt, files, 'split')
    made = []
    for num, start, stop in groups:
        if start > stop:
            continue
        writer = PdfWriter()
        for i in range(start, stop + 1):
            writer.add_page(doc.pages[i])
        name = unique(os.path.join(folder, '%s_p%03d-%03d.pdf' % (stem, start + 1, stop + 1)))
        with open(name, 'wb') as f:
            writer.write(f)
        made.append(name)
        log('  wrote %s (%d page%s)' % (os.path.basename(name), stop - start + 1,
                                        '' if stop == start else 's'))
    return 'Split %d pages into %d files inside %s' % (total, len(made), folder)


def _keep_drop(files, opt, log, keep):
    src = files[0]
    doc = reader_of(src, opt.get('password'))
    total = len(doc.pages)
    picked = set(parse_pages(opt['pages'], total))
    wanted = sorted(picked) if keep else [i for i in range(total) if i not in picked]
    if not wanted:
        raise ValueError('That leaves no pages at all, so nothing was written.')
    writer = PdfWriter()
    for i in wanted:
        writer.add_page(doc.pages[i])
    out = target(opt, src, 'extracted' if keep else 'trimmed')
    with open(out, 'wb') as f:
        writer.write(f)
    shown = ', '.join(str(i + 1) for i in wanted[:14]) + ('...' if len(wanted) > 14 else '')
    log('  pages in the new file: %s' % shown)
    if keep:
        return 'Kept %d of %d pages -> %s' % (len(wanted), total, out)
    return 'Removed %d of %d pages, %d left -> %s' % (len(picked), total, len(wanted), out)


def job_extract(files, opt, log):
    return _keep_drop(files, opt, log, keep=True)


def job_remove(files, opt, log):
    return _keep_drop(files, opt, log, keep=False)


def job_rearrange(files, opt, log):
    src = files[0]
    doc = reader_of(src, opt.get('password'))
    total = len(doc.pages)
    order = parse_pages(opt['pages'], total, repeats=True)
    preset = opt.get('preset', 'Use my order')
    if preset == 'Reverse':
        order = order[::-1]
    elif preset == 'Odd pages then even':
        order = [i for i in range(total) if i % 2 == 0] + [i for i in range(total) if i % 2]
    elif preset == 'Sort ascending':
        order = sorted(order)
    writer = PdfWriter()
    for i in order:
        writer.add_page(doc.pages[i])
    out = target(opt, src, 'rearranged')
    with open(out, 'wb') as f:
        writer.write(f)
    return 'Rewrote %d pages as %s -> %s' % (len(order), ', '.join(str(i + 1) for i in order[:12])
                                             + ('...' if len(order) > 12 else ''), out)


def job_rotate(files, opt, log):
    src = files[0]
    doc = reader_of(src, opt.get('password'))
    total = len(doc.pages)
    targets = set(parse_pages(opt['pages'], total))
    angle = int(opt['angle'])
    writer = PdfWriter()
    moved = 0
    for i, page in enumerate(doc.pages):
        if i in targets:
            page.rotate(angle)
            moved += 1
        writer.add_page(page)
    out = target(opt, src, 'rotated')
    with open(out, 'wb') as f:
        writer.write(f)
    return 'Turned %d page%s by %d degrees -> %s' % (moved, '' if moved == 1 else 's', angle, out)


def job_watermark(files, opt, log):
    need_fitz('Watermark')
    text = (opt.get('text') or '').strip()
    if not text:
        raise ValueError('Type the watermark text first.')
    size = float(opt.get('size') or 48)
    angle = float(opt.get('angle') or 45)
    opacity = float(opt.get('opacity') or 0.18)
    color = {'Grey': (0.55, 0.55, 0.55), 'Red': (0.8, 0.2, 0.2), 'Blue': (0.15, 0.3, 0.7),
             'Black': (0.1, 0.1, 0.1)}[opt.get('color', 'Grey')]
    where = opt.get('place', 'Centre, diagonal')
    src = files[0]
    doc = fitz.open(src)
    if doc.needs_pass:
        doc.authenticate(opt.get('password') or '')
    pages = set(parse_pages(opt.get('pages'), doc.page_count))
    for i in range(doc.page_count):
        if i not in pages:
            continue
        page = doc[i]
        w, h = page.rect.width, page.rect.height
        if where == 'Every page, tiled':
            step_x, step_y = size * 6, size * 8
            y = step_y / 2
            row = 0
            while y < h + step_y:
                x = (step_x / 2) - (step_x / 2 if row % 2 else 0)
                while x < w + step_x:
                    _stamp(page, x, y, text, size, angle, color, opacity, w, h)
                    x += step_x
                y += step_y
                row += 1
        else:
            spot = {'Top': (w / 2, size * 1.6), 'Bottom': (w / 2, h - size * 1.6),
                    'Centre, diagonal': (w / 2, h / 2)}[where]
            _stamp(page, spot[0], spot[1], text, size, angle, color, opacity, w, h)
        log('  stamped page %d' % (i + 1))
    out = target(opt, src, 'watermarked')
    doc.save(out, garbage=3, deflate=True)
    doc.close()
    return 'Watermarked %d page%s -> %s' % (len(pages), '' if len(pages) == 1 else 's', out)


def _stamp(page, cx, cy, text, size, angle, color, opacity, w, h):
    pivot = fitz.Point(cx, cy)
    where = fitz.Point(cx - len(text) * size * 0.28, cy + size * 0.32)
    page.insert_text(where, text, fontsize=size, fontname='helv', color=color,
                     fill_opacity=opacity, morph=(pivot, fitz.Matrix(-angle)))


def job_to_images(files, opt, log):
    need_fitz('Pages to images')
    src = files[0]
    doc = fitz.open(src)
    if doc.needs_pass:
        doc.authenticate(opt.get('password') or '')
    fmt = opt.get('format', 'PNG').lower()
    dpi = int(opt.get('dpi') or 150)
    zoom = dpi / 72.0
    pages = parse_pages(opt.get('pages'), doc.page_count)
    stem = os.path.splitext(os.path.basename(src))[0]
    folder = dest_folder(opt, files, 'pages')
    made = []
    for i in pages:
        pix = doc[i].get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        name = unique(os.path.join(folder, '%s_p%03d.%s' % (stem, i + 1, 'jpg' if fmt == 'jpg' else fmt)))
        pix.save(name)
        made.append(name)
        log('  %s  %dx%d px' % (os.path.basename(name), pix.width, pix.height))
    doc.close()
    return 'Rendered %d page%s at %d dpi into %s' % (len(made), '' if len(made) == 1 else 's',
                                                     dpi, folder)


def job_from_images(files, opt, log):
    if Image is None:
        raise RuntimeError('Images to PDF needs Pillow. Run: python -m pip install -r requirements.txt')
    pics = [f for f in files if os.path.splitext(f)[1].lower() in IMAGES]
    if not pics:
        raise ValueError('Add pictures (PNG or JPG) to the list first.')
    paper = PAPERS.get(opt.get('paper', 'Image size'))
    dpi = int(opt.get('dpi') or 150)
    margin = int(dpi / 12)
    frames = []
    for path in pics:
        with Image.open(path) as raw:
            img = raw.convert('RGB')
        if paper:
            canvas = (int(paper[0] * dpi) - 2 * margin, int(paper[1] * dpi) - 2 * margin)
            img.thumbnail(canvas, Image.LANCZOS)
            sheet = Image.new('RGB', (int(paper[0] * dpi), int(paper[1] * dpi)), 'white')
            sheet.paste(img, ((sheet.width - img.width) // 2, (sheet.height - img.height) // 2))
            img = sheet
        frames.append(img)
        log('  %s  %dx%d px' % (os.path.basename(path), img.width, img.height))
    out = target(opt, pics[0], 'from images')
    first, rest = frames[0], frames[1:]
    with open(out, 'wb') as f:
        first.save(f, 'PDF', save_all=True, append_images=rest, resolution=dpi)
    return 'Built a %d page PDF from %d picture%s -> %s' % (len(frames), len(pics),
                                                            '' if len(pics) == 1 else 's', out)


def job_to_png(files, opt, log):
    if Image is None:
        raise RuntimeError('Pictures to PNG needs Pillow. Run: python -m pip install -r requirements.txt')
    pics = [f for f in files if os.path.splitext(f)[1].lower() in IMAGES
            and not f.lower().endswith('.png')]
    if not pics:
        raise ValueError('Add JFIF or JPG pictures; a PNG is already a PNG.')
    folder = dest_folder(opt, files, 'png')
    made = []
    for path in pics:
        with Image.open(path) as raw:
            img = raw if raw.mode in ('1', 'L', 'LA', 'P', 'RGB', 'RGBA', 'I') else raw.convert('RGB')
            name = unique(os.path.join(folder, stem_of(path) + '.png'))
            img.save(name, 'PNG')
            made.append(name)
            log('  %s -> %s  %dx%d px' % (os.path.basename(path), os.path.basename(name),
                                          img.width, img.height))
    return 'Saved %d picture%s as PNG in %s' % (len(made), '' if len(made) == 1 else 's', folder)


def job_to_text(files, opt, log):
    together = opt.get('together') == 'All files in one .txt'
    chunks = []
    for path in files:
        doc = reader_of(path, opt.get('password'))
        pages = parse_pages(opt.get('pages'), len(doc.pages))
        body = '\n\n'.join((doc.pages[i].extract_text() or '') for i in pages)
        chunks.append((path, body))
        log('  %s: %d characters' % (os.path.basename(path), len(body)))

    if together:
        out = target(opt, files[0], 'text', '.txt')
        with open(out, 'w', encoding='utf-8') as f:
            for path, body in chunks:
                f.write('===== %s =====\n%s\n\n' % (os.path.basename(path), body))
        return 'Wrote the text of %d file%s -> %s' % (
            len(chunks), '' if len(chunks) == 1 else 's', out)

    folder = dest_folder(opt, files, 'text')
    made = []
    for path, body in chunks:
        name = unique(os.path.join(folder, stem_of(path) + '.txt'))
        with open(name, 'w', encoding='utf-8') as f:
            f.write(body)
        made.append(name)
        log('  wrote %s' % os.path.basename(name))
    return 'Wrote %d text file%s in %s' % (len(made), '' if len(made) == 1 else 's', folder)


def job_compress(files, opt, log):
    made = []
    for path in files:
        before = os.path.getsize(path)
        written = dest(opt, path, 'small')
        if fitz is not None:
            doc = fitz.open(path)
            if doc.needs_pass:
                doc.authenticate(opt.get('password') or '')
            doc.save(written, garbage=4, deflate=True, clean=True)
            doc.close()
        else:
            writer = PdfWriter(clone_from=path)
            for num, page in enumerate(writer.pages, 1):
                try:
                    page.compress_content_streams()
                except Exception as exc:
                    log('  page %d left as it is: %s' % (num, exc))
            with open(written, 'wb') as f:
                writer.write(f)
        after = os.path.getsize(written)
        made.append(written)
        pct = '%.0f%% smaller' % (100 - after * 100.0 / before) if before else 'same size'
        log('  %s: %s -> %s (%s)' % (stem_of(path), human(before), human(after), pct))
    return report(made, 'Compressed')


def job_protect(files, opt, log):
    user = opt.get('user') or ''
    owner = opt.get('owner') or user
    if not user and not owner:
        raise ValueError('Type a password, or the file would not be protected at all.')
    if opt.get('aes') == 'AES-256 (needs PyMuPDF)':
        need_fitz('AES-256')
    made = []
    for path in files:
        written = dest(opt, path, 'locked')
        if fitz is not None and opt.get('aes') == 'AES-256 (needs PyMuPDF)':
            doc = fitz.open(path)
            if doc.needs_pass:
                doc.authenticate(opt.get('password') or '')
            doc.save(written, encryption=fitz.PDF_ENCRYPT_AES_256,
                     user_pw=user or owner, owner_pw=owner or user, garbage=3, deflate=True)
            doc.close()
        else:
            writer = PdfWriter(clone_from=path)
            writer.encrypt(user_password=user or owner, owner_password=owner or user,
                           algorithm='RC4-128')
            with open(written, 'wb') as f:
                writer.write(f)
        made.append(written)
        log('  locked %s' % written)
    return report(made, 'Protected')


def job_unlock(files, opt, log):
    pw = opt.get('password') or opt.get('user') or ''
    made = []
    for path in files:
        written = dest(opt, path, 'open')
        if fitz is not None:
            doc = fitz.open(path)
            if doc.needs_pass and not doc.authenticate(pw):
                doc.close()
                raise ValueError('That password does not open %s.' % os.path.basename(path))
            doc.save(written, encryption=fitz.PDF_ENCRYPT_NONE,
                     garbage=3, deflate=True)
            doc.close()
        else:
            doc = PdfReader(path)
            if doc.is_encrypted and not doc.decrypt(pw):
                raise ValueError('That password does not open %s.' % os.path.basename(path))
            writer = PdfWriter()
            for page in doc.pages:
                writer.add_page(page)
            with open(written, 'wb') as f:
                writer.write(f)
        made.append(written)
        log('  opened %s' % written)
    return report(made, 'Removed the password from')


def job_info(files, opt, log):
    for path in files:
        doc = reader_of(path, opt.get('password'))
        size = os.path.getsize(path)
        meta = doc.metadata or {}
        big = sorted(((len((doc.pages[i].extract_text() or '')), i + 1)
                      for i in range(min(len(doc.pages), 60))), reverse=True)[:3]
        log('%s' % os.path.basename(path))
        log('  pages      %d   (%s each)' % (len(doc.pages), paper_name(doc.pages[0])))
        log('  file       %s   PDF %s   %s' % (human(size), pdf_version(path),
                                               'password protected' if doc.is_encrypted else 'no password'))
        log('  title      %s' % (getattr(meta, 'title', None) or '-'))
        log('  author     %s' % (getattr(meta, 'author', None) or '-'))
        log('  subject    %s' % (getattr(meta, 'subject', None) or '-'))
        log('  created    %s   modified %s' % (getattr(meta, 'creation_date', None) or '-',
                                               getattr(meta, 'modification_date', None) or '-'))
        log('  heaviest   %s' % ', '.join('p%d (%d chars)' % (n, c) for c, n in big if c))
        log('  text check %d page%s had no letters at all' % (
            sum(1 for i in range(len(doc.pages)) if not (doc.pages[i].extract_text() or '').strip()),
            '' if sum(1 for i in range(len(doc.pages))
                      if not (doc.pages[i].extract_text() or '').strip()) == 1 else 's'))
    return 'Read %d file%s' % (len(files), '' if len(files) == 1 else 's')


def job_metadata(files, opt, log):
    src = files[0]
    writer = PdfWriter(clone_from=src)
    # pypdf wants the raw PDF key names, slash included.
    writer.add_metadata({'/Title': opt.get('title') or '', '/Author': opt.get('author') or '',
                         '/Subject': opt.get('subject') or '', '/Creator': 'PDF Studio',
                         '/Producer': 'PDF Studio'})
    for key in ('Title', 'Author', 'Subject'):
        value = opt.get(key.lower()) or ''
        if value:
            log('  %s = %s' % (key.lower(), value))
    out = target(opt, src, 'labelled')
    with open(out, 'wb') as f:
        writer.write(f)
    return 'Wrote the title, author and subject -> %s' % out


def job_stamp(files, opt, log):
    src = files[0]
    doc = reader_of(src, opt.get('password'))
    total = len(doc.pages)
    first = int(opt.get('start') or 1)
    pattern = opt.get('text') or 'Page {n} of {total}'
    writer = PdfWriter()
    last = ''
    for i, page in enumerate(doc.pages):
        last = pattern.replace('{n}', str(i + first)).replace('{total}', str(total + first - 1))
        try:
            page.merge_page(_number_page(last, page, opt.get('place', 'Bottom centre')))
        except Exception as exc:
            log('  page %d skipped: %s' % (i + 1, exc))
        writer.add_page(page)
    out = target(opt, src, 'numbered')
    with open(out, 'wb') as f:
        writer.write(f)
    return 'Printed "%s" style numbers on %d page%s -> %s' % (
        last, total, '' if total == 1 else 's', out)


def _number_page(text, page, place):
    """A one-off PDF page holding the footer text, drawn with Pillow."""
    if Image is None:
        raise RuntimeError('Page numbers needs Pillow.')
    from PIL import ImageDraw, ImageFont
    w, h = float(page.mediabox.width), float(page.mediabox.height)
    img = Image.new('RGBA', (int(w), int(h)))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype('arial.ttf', max(10, int(h * 0.022)))
    except Exception:
        font = ImageFont.load_default()
    box = draw.textbbox((0, 0), text, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    side = {'left': w * 0.04, 'right': w - tw - w * 0.04, 'centre': (w - tw) / 2}[
        place.split()[-1]]
    y = h * 0.03 if place.startswith('Top') else h - th - h * 0.03
    draw.text((side, y), text, font=font, fill=(0, 0, 0, 255))
    buf = io.BytesIO()
    img.save(buf, 'PDF')
    buf.seek(0)
    return PdfReader(buf).pages[0]


# ---------------------------------------------------------------------- the map
class Field(object):
    def __init__(self, key, kind, label, default=None, choices=None, help_text=''):
        self.key, self.kind, self.label = key, kind, label
        self.default, self.choices, self.help_text = default, choices, help_text


class Tool(object):
    def __init__(self, name, blurb, run, needs='pdf', many=False, fields=(),
                 batch=False, ordered=False, out_ext='.pdf', writes=True):
        self.name, self.blurb, self.run = name, blurb, run
        self.needs, self.many, self.fields = needs, many, fields
        # batch: writes several files, so "Save as" asks for a folder instead.
        # ordered: the row order in the file list is what the job uses.
        self.batch, self.ordered, self.out_ext = batch, ordered, out_ext
        self.writes = writes


PW = Field('password', 'entry', 'If the file is locked, its password', '', 'Password to open it.')
TOOLS = [
    Tool('Merge PDFs', 'Put several PDFs into one, in the order listed.', job_merge, many=True,
         ordered=True, fields=(PW,)),
    Tool('Split into parts', 'Cut one PDF into smaller files.', job_split, batch=True,
         fields=(Field('mode', 'choice', 'Split by', 'Every N pages',
                       ('One file per page', 'Every N pages', 'Cut after these pages')),
                 Field('value', 'entry', 'N, or the cut points', '3', 'e.g. 3, or 2-4 for after pages 2 and 4.'),
                 PW)),
    Tool('Extract pages', 'Keep only the pages you list.', job_extract,
         fields=(Field('pages', 'entry', 'Pages to keep', '1-3', 'Ranges work: 1,4-6,even.'), PW)),
    Tool('Remove pages', 'Drop the pages you list, keep the rest.', job_remove,
         fields=(Field('pages', 'entry', 'Pages to remove', '2', 'Ranges work: 1,4-6,odd.'), PW)),
    Tool('Rearrange pages', 'A new order, or a preset shuffle.', job_rearrange,
         fields=(Field('pages', 'entry', 'Order', '2,1,3', 'Comma list, repeats allowed.'),
                 Field('preset', 'choice', 'Then apply', 'Use my order',
                       ('Use my order', 'Reverse', 'Sort ascending', 'Odd pages then even')), PW)),
    Tool('Rotate pages', 'Turn chosen pages by 90, 180 or 270.', job_rotate,
         fields=(Field('angle', 'choice', 'Turn by', '90', ('90', '180', '270')),
                 Field('pages', 'entry', 'Which pages', ALL), PW)),
    Tool('Watermark', 'Text across the page, faded so the print still reads.', job_watermark,
         fields=(Field('text', 'entry', 'Watermark text', 'DRAFT'),
                 Field('size', 'entry', 'Text size', '48'),
                 Field('angle', 'entry', 'Angle in degrees', '45'),
                 Field('opacity', 'entry', 'How faint, 0.05 to 0.9', '0.18'),
                 Field('color', 'choice', 'Colour', 'Grey', ('Grey', 'Red', 'Blue', 'Black')),
                 Field('place', 'choice', 'Where', 'Centre, diagonal',
                       ('Centre, diagonal', 'Top', 'Bottom', 'Every page, tiled')),
                 Field('pages', 'entry', 'Which pages', ALL), PW)),
    Tool('Page numbers', 'Print "Page 1 of 12" without moving anything.', job_stamp,
         fields=(Field('text', 'entry', 'What to print', 'Page {n} of {total}',
                       '{n} and {total} are replaced.'),
                 Field('place', 'choice', 'Where', 'Bottom centre',
                       ('Bottom centre', 'Bottom left', 'Bottom right', 'Top left', 'Top right')),
                 Field('start', 'entry', 'Number the first page as', '1'), PW)),
    Tool('Pages to images', 'Render pages as PNG or JPG for slides and sheets.', job_to_images,
         batch=True,
         fields=(Field('format', 'choice', 'Format', 'PNG', ('PNG', 'JPG')),
                 Field('dpi', 'entry', 'Dots per inch', '150', '150 is screen, 300 is print.'),
                 Field('pages', 'entry', 'Which pages', ALL), PW)),
    Tool('Images to PDF', 'Turn pictures into one PDF, one page each.', job_from_images,
         needs='image', many=True, ordered=True,
         fields=(Field('paper', 'choice', 'Page size', 'A4',
                       ('Image size', 'A4', 'Letter', 'Legal'), 'White paper with the picture centred.'),
                 Field('dpi', 'entry', 'Dots per inch', '150',
                       'On "Image size" paper this decides how large the picture prints.'))),
    Tool('JFIF to PNG', 'Save .jfif and .jpg pictures as clean PNG copies.', job_to_png,
         needs='image', many=True, batch=True, out_ext='.png'),
    Tool('Extract text', 'The words in a PDF, as a plain .txt you can paste.', job_to_text,
         many=True, batch=True, out_ext='.txt',
         fields=(Field('pages', 'entry', 'Which pages', ALL),
                 Field('together', 'choice', 'Output', 'One .txt per PDF',
                       ('One .txt per PDF', 'All files in one .txt')), PW)),
    Tool('Compress', 'Rewrite the file smaller. Good before sending by mail.', job_compress,
         many=True, batch=True, fields=(PW,)),
    Tool('Protect with a password', 'Lock the file so it needs a password.', job_protect,
         many=True, batch=True,
         fields=(Field('user', 'entry', 'Password to open', '', 'Shown as dots by the reader.'),
                 Field('owner', 'entry', 'Password to change it (optional)'),
                 Field('aes', 'choice', 'Strength', 'AES-256 (needs PyMuPDF)',
                       ('AES-256 (needs PyMuPDF)', 'RC4-128 (old readers)')))),
    Tool('Remove the password', 'Save an open copy of a locked PDF.', job_unlock, many=True,
         batch=True,
         fields=(Field('password', 'entry', 'Its current password', ''),)),
    Tool('File report', 'Pages, paper size, author, and where the text is thin.', job_info,
         many=True, writes=False, fields=(PW,)),
    Tool('Edit title and author', 'The document properties a reader shows.', job_metadata,
         fields=(Field('title', 'entry', 'Title'), Field('author', 'entry', 'Author'),
                 Field('subject', 'entry', 'Subject'))),
]


def tool_named(name):
    """The Tool whose name was posted, or None when it is not on the list."""
    for tool in TOOLS:
        if tool.name == name:
            return tool
    return None


def defaults(tool):
    """Every field's starting value, so a missing form box cannot crash a job."""
    return {field.key: ('' if field.default is None else str(field.default))
            for field in tool.fields}
