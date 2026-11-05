"""One-click, private, resumable Wikimedia dump importer; no admin or engine modifications."""
from __future__ import annotations

import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

SCRIPT=Path(__file__).resolve().with_name('import_dumps.py')
INSTANCE=SCRIPT.parents[3]  # .../tools/wiki/dump_import/import_dumps.py -> instance root
DUMPS=Path(r'D:\EncyKlopedia\10_sources\wikipedia\enwiki\2026-10')
INDEX=Path(r'D:\EncyKlopedia\80_search_indexes\mediatheque-references\wikipedia_en.sqlite')


def main():
    root=tk.Tk()
    root.title('Médiathèque Références — Import massif Wikimedia EN (hors ligne)')
    root.geometry('1040x680')
    area=ttk.Frame(root,padding=12);area.pack(fill='both',expand=True)
    ttk.Label(area,text='IMPORT MASSIF WIKIPÉDIA EN / WIKIDATA',font=('Segoe UI',14,'bold')).pack(anchor='w')
    ttk.Label(area,text='7 archives locales sur D: · index SQLite massif sur D: · reprise automatique · moteur Médiathèque inchangé',wraplength=980).pack(anchor='w',pady=4)
    for x in (f'Instance : {INSTANCE}',f'Archives : {DUMPS}',f'Base massive : {INDEX}'):
        ttk.Label(area,text=x).pack(anchor='w')
    ttk.Label(area,text='Le texte XML reste archivé au format compressé. Les titres, QID, révisions et liens SQL sont indexés. Cela ne vérifie PAS les faits cités.',wraplength=980).pack(anchor='w',pady=7)
    bar=ttk.Frame(area);bar.pack(fill='x',pady=8)
    log=tk.Text(area,wrap='word',height=30,font=('Consolas',10));log.pack(side='left',fill='both',expand=True)
    scroll=ttk.Scrollbar(area,command=log.yview);scroll.pack(side='right',fill='y');log.configure(yscrollcommand=scroll.set)
    status=tk.StringVar(value='Inactif : vérifier les archives avant de lancer.');ttk.Label(bar,textvariable=status).pack(side='right')
    inbox=queue.Queue(); active={'p':None}
    logfile=INSTANCE/'08_LOGS'/('Wikipedia_Dumps_'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.log')
    logfile.parent.mkdir(parents=True,exist_ok=True)
    def show(text):
        log.insert('end',f'{datetime.now():%H:%M:%S}  {text}\n');log.see('end')
    def run(action):
        if active['p'] and active['p'].poll() is None:
            messagebox.showinfo('Import en cours','Une seule opération à la fois.');return
        if action=='run':
            if not messagebox.askyesno('Démarrer l’import massif',
                'La base D: peut occuper des centaines de Go et le travail peut être très long.\n\n'
                'Aucun fichier source ne sera effacé. Le moteur et la base centrale C: resteront intacts.\n\nDémarrer l’import complet ?'):
                return
        cmd=[sys.executable,str(SCRIPT),action]
        status.set('En cours : '+action)
        show('> '+ ' '.join(cmd))
        def worker():
            try:
                flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
                p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                   text=True,encoding='utf-8',errors='replace',bufsize=1,creationflags=flags)
                active['p']=p
                with logfile.open('a',encoding='utf8') as saved:
                    for line in p.stdout:
                        saved.write(line); saved.flush()
                        inbox.put(('line',line.rstrip()))
                code=p.wait();inbox.put(('done',code))
            except Exception as exc: inbox.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()
    def stop():
        p=active['p']
        if p and p.poll() is None and messagebox.askyesno('Interrompre','Arrêter maintenant ? La prochaine exécution reprendra au dernier checkpoint validé.'):
            p.terminate();show('Arrêt demandé; reprise possible.')
    ttk.Button(bar,text='1. Vérifier les 7 fichiers',command=lambda:run('plan')).pack(side='left',padx=3)
    ttk.Button(bar,text='2. IMPORTER TOUT',command=lambda:run('run')).pack(side='left',padx=3)
    ttk.Button(bar,text='3. État / reprendre',command=lambda:run('status')).pack(side='left',padx=3)
    ttk.Button(bar,text='Arrêter',command=stop).pack(side='left',padx=3)
    def pump():
        try:
            while True:
                kind,x=inbox.get_nowait()
                if kind=='line':
                    try:
                        obj=json.loads(x); key=obj.get('event', '');
                        if key=='progress': status.set(f"{obj.get('stage')}: {obj.get('rows',0):,} rangées".replace(',',' '))
                        elif key=='stage_complete':status.set(f"{obj.get('stage')}: étape terminée")
                        elif key=='error':status.set('ERREUR — voir journal')
                    except (ValueError,TypeError): pass
                    show(x)
                elif kind=='done': status.set('Terminé' if x==0 else f'Arrêt / erreur (code {x}), reprise possible');show(f'Code de sortie: {x}');active['p']=None
                else: status.set('Erreur');show(str(x));active['p']=None
        except queue.Empty: pass
        root.after(150,pump)
    def close():
        if active['p'] and active['p'].poll() is None:
            messagebox.showwarning('Import en cours','Utilise Arrêter avant de fermer pour enregistrer un checkpoint cohérent.');return
        root.destroy()
    root.protocol('WM_DELETE_WINDOW',close)
    show('Journal permanent : '+str(logfile))
    show('Commencer par 1. Vérifier les 7 fichiers. Puis 2. IMPORTER TOUT. En cas d’arrêt, relancer 2 pour reprendre.')
    pump();root.mainloop()

if __name__=='__main__':main()
