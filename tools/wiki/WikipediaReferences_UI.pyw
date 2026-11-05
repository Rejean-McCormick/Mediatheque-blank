"""Optional local GUI for the private Wikipedia reference inventory workflow."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

HERE = Path(__file__).resolve().parent
TOOL = HERE / 'WikipediaReferenceInventory.py'
TITLES = HERE / 'educational_policy_en.txt'
DEFAULT_INSTANCE = HERE.parents[1]


def main():
    root=tk.Tk()
    root.title('Médiathèque — Inventaire Wikipédia EN (privé)')
    root.geometry('920x590')
    frm=ttk.Frame(root,padding=14)
    frm.pack(fill='both',expand=True)
    ttk.Label(frm,text='Wikipedia EN → Médiathèque : sources et références candidates',font=('Segoe UI',12,'bold')).pack(anchor='w')
    ttk.Label(frm,text='Aucune publication ni création KA/KS. Collecte uniquement les six pages sélectionnées.').pack(anchor='w',pady=(0,10))
    instance=tk.StringVar(value=str(DEFAULT_INSTANCE))
    contact=tk.StringVar()
    manifest=tk.StringVar()
    for label,var in [('Instance privée (base déjà initialisée)',instance),('Contact pour Wikimedia (adresse e-mail ou URL https)',contact),('Manifeste JSON produit par la collecte',manifest)]:
        row=ttk.Frame(frm)
        row.pack(fill='x',pady=3)
        ttk.Label(row,text=label,width=47).pack(side='left')
        ttk.Entry(row,textvariable=var, state=('readonly' if var is instance else 'normal')).pack(side='left',fill='x',expand=True)
        if var is manifest:
            ttk.Button(row,text='Parcourir…',command=lambda:manifest.set(filedialog.askopenfilename(filetypes=[('JSON','*.json')]) or manifest.get())).pack(side='left',padx=4)
    log=tk.Text(frm,height=20,wrap='word',state='disabled')
    def append(message):
        log.configure(state='normal'); log.insert('end',message+'\n'); log.see('end'); log.configure(state='disabled')
    buttons=ttk.Frame(frm)
    buttons.pack(fill='x',pady=8)
    def run_async(command):
        command = list(command)
        for widget in buttons.winfo_children(): widget.configure(state='disabled')
        def work():
            try:
                proc=subprocess.run([sys.executable,str(TOOL),*command],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=900)
                message=(proc.stdout or '')+('\n'+proc.stderr if proc.stderr else '')
                root.after(0,lambda:append(message.strip() or f'Code: {proc.returncode}'))
            except Exception as exc:
                root.after(0,lambda:append('ERROR: '+str(exc)))
            finally:
                root.after(0,lambda:[w.configure(state='normal') for w in buttons.winfo_children()])
        threading.Thread(target=work,daemon=True).start()
    def collect():
        base=Path(instance.get()).expanduser()
        if not contact.get().strip():
            messagebox.showerror('Contact requis','Saisir un contact réel pour le User-Agent Wikimedia.');return
        out=base/'03_IMPORTS'/'wikipedia'/('educational-policy-en-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.json')
        manifest.set(str(out))
        append('Collecte Wikimedia API : 6 pages, requêtes séquentielles et captures privées…')
        run_async(['collect','--titles',str(TITLES),'--output',str(out),'--contact',contact.get().strip()])
    def plan():
        if not manifest.get():
            messagebox.showerror('Manifeste requis','Effectuer Collecter ou choisir un manifeste.');return
        run_async(['plan','--manifest',manifest.get()])
    def apply():
        if not manifest.get():
            messagebox.showerror('Manifeste requis','Choisir un manifeste.');return
        if not messagebox.askyesno('Importer dans la médiathèque privée?',
            'Une sauvegarde SQLite sera créée avant écriture.\nSeules des URLs déclarées et des relations de découverte non vérifiées seront ajoutées.\nAucune assertion canonique ni publication. Continuer?'):
            return
        run_async(['import','--accept','--manifest',manifest.get()])
    ttk.Button(buttons,text='1. Collecter 6 articles',command=collect).pack(side='left',padx=3)
    ttk.Button(buttons,text='2. Vérifier (lecture seule)',command=plan).pack(side='left',padx=3)
    ttk.Button(buttons,text='3. Importer dans la base',command=apply).pack(side='left',padx=3)
    def export():
        base=Path(instance.get())
        outfile=base/'04_EXPORTS'/'wikipedia'/('educational-policy-en-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.csv')
        run_async(['export','--output',str(outfile)])
    ttk.Button(buttons,text='4. Exporter CSV',command=export).pack(side='left',padx=3)
    log.pack(fill='both',expand=True)
    append('Instance suggérée : C:\\mycode\\mediatheque-unesco (copie privée de mediatheque-blank, avec id unique et base initialisée).')
    append('La collecte ne télécharge PAS les sites cités, seulement les pages Wikipédia retenues.')
    root.mainloop()


if __name__=='__main__':
    main()
