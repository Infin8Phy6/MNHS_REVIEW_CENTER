"""PDF Studio - every PDF and picture job in one window.

    python -m venv .venv
    .venv\\Scripts\\activate
    python -m pip install -r requirements.txt
    python pdf_studio.py

Pick a tool on the left, drop the files in (or press Add PDFs), set the few
choices, press Run. Leaving "Save as" empty writes a new file beside the source
and never overwrites one - a second run makes "... (2).pdf".

The jobs themselves live in pdf_tools.py, which has no window and is also what
the staff page (/staff/pdf-studio) runs on the server. This file only draws the
window, so the two copies of PDF Studio always offer the same tools.
"""
import os
import queue
import threading
import traceback
from datetime import datetime

import tkinter as tk
from tkinter import Text, filedialog, messagebox, ttk, StringVar

from pdf_tools import *                  # noqa: F401,F403  (the jobs and TOOLS)
from pdf_tools import (                 # named again so editors can see the use
    HAS_CRYPTO, IMAGES, TOOLS, fitz, human, pypdf, Image,
)

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except Exception:
    TkinterDnD, DND_FILES, HAS_DND = None, None, False


class Studio(object):
    def __init__(self, root):
        self.root = root
        self.files = []
        self.vars = {}
        self.busy = False
        self.jobs = queue.Queue()
        root.title('PDF Studio')
        root.geometry('1020x680')
        root.minsize(760, 520)
        style = ttk.Style(root)
        if 'clam' in style.theme_names():
            style.theme_use('clam')
        style.configure('Tool.TButton', padding=6)
        style.configure('Run.TButton', padding=(18, 9), font=('Segoe UI', 11, 'bold'))

        top = ttk.Frame(root, padding=(12, 10, 12, 4))
        top.pack(fill='x')
        ttk.Label(top, text='PDF Studio', font=('Segoe UI', 15, 'bold')).pack(side='left')
        parts = ['pypdf %s' % pypdf.__version__,
                 'PyMuPDF %s' % fitz.version[0] if fitz else 'no PyMuPDF',
                 'Pillow %s' % Image.__version__ if Image else 'no Pillow',
                 'AES reads %s' % ('on' if HAS_CRYPTO else 'off'),
                 'drag and drop %s' % ('on' if HAS_DND else 'off')]
        ttk.Label(top, text='   ·   '.join(parts), foreground='#556').pack(side='right')

        body = ttk.PanedWindow(root, orient='horizontal')
        body.pack(fill='both', expand=True, padx=12, pady=6)

        left = ttk.Frame(body, width=210)
        body.add(left, weight=0)
        ttk.Label(left, text='Tools', font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        self.tool_list = ttk.Treeview(left, show='tree', selectmode='browse')
        self.tool_list.pack(fill='both', expand=True, pady=4)
        for tool in TOOLS:
            self.tool_list.insert('', 'end', text=tool.name)
        self.blurb = ttk.Label(left, text='', wraplength=190, foreground='#445', justify='left')
        self.blurb.pack(anchor='w', pady=(0, 6))

        right = ttk.Frame(body)
        body.add(right, weight=1)

        files_card = ttk.LabelFrame(right, text='Files - first one is the main file', padding=8)
        files_card.pack(fill='x', pady=(0, 6))
        row = ttk.Frame(files_card)
        row.pack(fill='x')
        for label, cmd in (('Add PDFs', lambda: self.pick('pdf')),
                           ('Add pictures', lambda: self.pick('image')),
                           ('Remove', self.remove_file), ('Up', lambda: self.move(-1)),
                           ('Down', lambda: self.move(1)), ('Clear', self.clear_files)):
            ttk.Button(row, text=label, command=cmd, style='Tool.TButton').pack(side='left', padx=2)
        self.files_hint = ttk.Label(files_card, text='', foreground='#556')
        self.files_hint.pack(anchor='w', pady=(4, 0))
        hold = ttk.Frame(files_card)
        hold.pack(fill='x', pady=(2, 0))
        self.file_view = ttk.Treeview(hold, columns=('n', 'size'), show='tree headings', height=6)
        self.file_view.heading('#0', text='#')
        self.file_view.heading('n', text='File')
        self.file_view.heading('size', text='Size')
        self.file_view.column('#0', width=28, stretch=False)
        self.file_view.column('n', width=460)
        self.file_view.column('size', width=70, anchor='e')
        bar = ttk.Scrollbar(hold, orient='vertical', command=self.file_view.yview)
        self.file_view.configure(yscrollcommand=bar.set)
        self.file_view.pack(side='left', fill='both', expand=True)
        bar.pack(side='left', fill='y')

        self.settings = ttk.LabelFrame(right, text='Settings', padding=8)
        self.settings.pack(fill='x', pady=6)

        outrow = ttk.Frame(right)
        outrow.pack(fill='x', pady=(0, 6))
        ttk.Label(outrow, text='Save as').pack(side='left')
        self.out_var = StringVar()
        self.out_entry = ttk.Entry(outrow, textvariable=self.out_var)
        self.out_entry.pack(side='left', fill='x', expand=True, padx=6)
        self.out_browse = ttk.Button(outrow, text='Browse', command=self.choose_out, width=8)
        self.out_browse.pack(side='left')
        self.out_default = ttk.Button(outrow, text='Default',
                                      command=lambda: self.out_var.set(''), width=8)
        self.out_default.pack(side='left', padx=3)

        runrow = ttk.Frame(right)
        runrow.pack(fill='x', pady=(0, 4))
        self.run_btn = ttk.Button(runrow, text='Run', command=self.run, style='Run.TButton')
        self.run_btn.pack(side='left')
        self.reveal = ttk.Button(runrow, text='Open the folder', command=self.show_output)
        self.reveal.pack(side='left', padx=10)
        self.out_hint = ttk.Label(runrow, text='', foreground='#778')
        self.out_hint.pack(side='left', padx=6)
        self.status = ttk.Label(runrow, text='', foreground='#12263f')
        self.status.pack(side='right')

        log_card = ttk.LabelFrame(right, text='Log', padding=6)
        log_card.pack(fill='both', expand=True)
        self.log_box = Text(log_card, height=9, wrap='word', background='#fbfbfd',
                            font=('Consolas', 9), relief='flat')
        lbar = ttk.Scrollbar(log_card, orient='vertical', command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=lbar.set, state='disabled')
        self.log_box.pack(side='left', fill='both', expand=True)
        lbar.pack(side='left', fill='y')
        ttk.Button(root, text='Clear log', command=self.clear_log).pack(anchor='e', padx=14, pady=(0, 8))

        self.tool_list.bind('<<TreeviewSelect>>', self.build_settings)
        first = self.tool_list.get_children()[0]
        self.tool_list.selection_set(first)
        self.tool_list.focus(first)
        self.build_settings()

        if HAS_DND:
            root.drop_target_register(DND_FILES)
            root.dnd_bind('<<Drop>>', self.on_drop)
        self.last_out = None
        root.after(120, self.pump)
        root.protocol('WM_DELETE_WINDOW', self.quit)

    # ---- the file list
    def pick(self, kind):
        exts = ('*.pdf',) if kind == 'pdf' else tuple('*' + e for e in IMAGES)
        for path in filedialog.askopenfilenames(filetypes=[('Files', ' '.join(exts))]):
            self.add_file(path)
        self.refresh_files()

    def add_file(self, path):
        path = path.strip('{}').strip('"')
        if os.path.isdir(path):
            found = sorted(os.path.join(path, n) for n in os.listdir(path)
                           if n.lower().endswith('.pdf'))
            for one in found:
                self.add_file(one)
            return
        if path.lower().endswith('.pdf') or os.path.splitext(path)[1].lower() in IMAGES:
            if path not in self.files:
                self.files.append(path)

    def remove_file(self):
        sel = self.file_view.selection()
        for s in sel:
            n = int(self.file_view.item(s)['text']) - 1
            if 0 <= n < len(self.files):
                self.files[n] = None
        self.files = [f for f in self.files if f]
        self.refresh_files()

    def move(self, delta):
        sel = self.file_view.selection()
        if not sel:
            return
        i = int(self.file_view.item(sel[0])['text']) - 1
        j = min(max(i + delta, 0), len(self.files) - 1)
        self.files[i], self.files[j] = self.files[j], self.files[i]
        self.refresh_files(keep=i)

    def clear_files(self):
        self.files = []
        self.refresh_files()

    def refresh_files(self, keep=None):
        self.file_view.delete(*self.file_view.get_children())
        for i, path in enumerate(self.files, 1):
            size = human(os.path.getsize(path)) if os.path.exists(path) else 'missing'
            node = self.file_view.insert('', 'end', text=str(i),
                                         values=(os.path.basename(path), size))
            if keep is not None and i == keep + 1:
                self.file_view.selection_set(node)
        tool = self.current()
        want = 'PDF files' if tool.needs == 'pdf' else 'picture files'
        self.files_hint.config(text='%d in the list. This tool wants %s.%s' % (
            len(self.files), want,
            '  The order in the list is the order it uses.' if tool.ordered else ''))

    def on_drop(self, event):
        for path in self.root.tk.splitlist(event.data):
            self.add_file(path)
        self.refresh_files()

    # ---- the settings panel
    def current(self):
        sel = self.tool_list.selection()
        idx = int(self.tool_list.index(sel[0])) if sel else 0
        return TOOLS[idx]

    def build_settings(self, *_):
        for child in self.settings.winfo_children():
            child.destroy()
        tool = self.current()
        self.blurb.config(text=tool.blurb)
        self.vars = {}
        for n, field in enumerate(tool.fields):
            label = ttk.Label(self.settings, text=field.label)
            label.grid(row=n, column=0, sticky='w', pady=2, padx=(0, 8))
            var = StringVar(value='' if field.default is None else str(field.default))
            self.vars[field.key] = var
            if field.kind == 'choice':
                box = ttk.Combobox(self.settings, textvariable=var, state='readonly',
                                   values=list(field.choices), width=26)
                box.grid(row=n, column=1, sticky='w')
            else:
                box = ttk.Entry(self.settings, textvariable=var, width=40,
                                show='*' if field.key in ('password', 'user', 'owner') else '')
                box.grid(row=n, column=1, sticky='w')
                if field.help_text:
                    tip = ttk.Label(self.settings, text=field.help_text, foreground='#778')
                    tip.grid(row=n, column=2, sticky='w', padx=10)
                    box.bind('<FocusIn>', lambda e, t=tip: t.config(foreground='#12263f'))
                    box.bind('<FocusOut>', lambda e, t=tip: t.config(foreground='#778'))
        self.settings.columnconfigure(1, weight=1)
        on = ('!disabled',) if tool.writes else ('disabled',)
        for widget in (self.out_entry, self.out_browse, self.out_default):
            widget.state(on)
        if not tool.writes:
            self.out_var.set('')
        self.out_hint.config(text=(
            'This one only prints to the log below.' if not tool.writes else
            'Empty means a new folder beside the source.' if tool.batch else
            'Empty means a new file beside the source.'))
        self.refresh_files()

    def choose_out(self):
        tool = self.current()
        if not tool.writes:
            return
        if tool.batch:
            path = filedialog.askdirectory(title='Folder for the results')
        else:
            path = filedialog.asksaveasfilename(defaultextension=tool.out_ext,
                                                filetypes=[('Output', '*' + tool.out_ext)])
        if path:
            self.out_var.set(path)

    # ---- running
    def run(self):
        if self.busy:
            return
        tool = self.current()
        if not self.files:
            messagebox.showinfo('Nothing to do', 'Add at least one file to the list first.')
            return
        missing = [f for f in self.files if not os.path.exists(f)]
        if missing:
            messagebox.showinfo('File gone', '%s is not there anymore.\n'
                                'Remove it from the list and try again.'
                                % os.path.basename(missing[0]))
            return
        if tool.needs == 'pdf':
            wrong = [f for f in self.files if not f.lower().endswith('.pdf')]
            if wrong:
                messagebox.showinfo('Wrong file', 'This tool works on PDFs only:\n%s'
                                    % os.path.basename(wrong[0]))
                return
        if tool.needs == 'image' and not any(os.path.splitext(f)[1].lower() in IMAGES
                                             for f in self.files):
            messagebox.showinfo('Wrong file', 'Add the pictures this tool works on.')
            return
        opt = {f.key: self.vars[f.key].get() for f in tool.fields}
        out = self.out_var.get().strip()
        if out:
            opt['out'] = out if os.path.isdir(out) else os.path.abspath(out)
        files = list(self.files)
        self.busy = True
        self.run_btn.state(('disabled',))
        self.status.config(text='working...')
        self.log('=== %s · %s' % (tool.name, datetime.now().strftime('%H:%M:%S')))
        threading.Thread(target=self._worker, args=(tool, files, opt), daemon=True).start()

    def _worker(self, tool, files, opt):
        try:
            done = tool.run(files, opt, lambda line: self.jobs.put(('log', line)))
            self.jobs.put(('done', done, tool.name, opt.get('out')))
        except Exception as exc:
            note = str(exc) or exc.__class__.__name__
            self.jobs.put(('fail', note, tool.name, traceback.format_exc()))

    def pump(self):
        try:
            while True:
                item = self.jobs.get_nowait()
                if item[0] == 'log':
                    self.log(item[1])
                elif item[0] == 'done':
                    self.busy = False
                    self.run_btn.state(('!disabled',))
                    self.status.config(text='done')
                    self.last_out = item[3] or self.files[0]
                    self.log(item[1])
                    messagebox.showinfo(item[2], item[1])
                else:
                    self.busy = False
                    self.run_btn.state(('!disabled',))
                    self.status.config(text='stopped')
                    self.log('!! ' + item[1])
                    self.log('\n'.join('   ' + n for n in item[3].strip().splitlines()[-4:]))
                    messagebox.showerror(item[2], item[1])
        except queue.Empty:
            pass
        self.root.after(150, self.pump)

    def log(self, line):
        self.log_box.configure(state='normal')
        self.log_box.insert('end', line.rstrip() + '\n')
        self.log_box.see('end')
        self.log_box.configure(state='disabled')

    def clear_log(self):
        self.log_box.configure(state='normal')
        self.log_box.delete('1.0', 'end')
        self.log_box.configure(state='disabled')

    def show_output(self):
        path = self.last_out or (self.files[0] if self.files else '')
        if not path or not os.path.exists(path):
            messagebox.showinfo('Nothing yet', 'Run a tool first.')
            return
        folder = path if os.path.isdir(path) else os.path.dirname(path)
        try:
            if os.name == 'nt':
                os.startfile(folder)                                    # noqa: S606
            else:
                import subprocess
                subprocess.Popen(['xdg-open', folder])
        except Exception as exc:
            self.log('Could not open the folder: %s' % exc)

    def quit(self):
        self.root.destroy()


def main():
    root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
    Studio(root)
    root.mainloop()


if __name__ == '__main__':
    main()
