"""Native Windows UI plus automation-friendly read-only scan/build commands."""
import argparse
import ctypes
import json
import pathlib
import sys
import os

BASE = pathlib.Path(sys.executable).parent if getattr(sys,'frozen',False) else pathlib.Path(__file__).parent

def main():
    parser=argparse.ArgumentParser(description='Limbus AI Bridge')
    parser.add_argument('--scan',action='store_true')
    parser.add_argument('--build',action='store_true')
    parser.add_argument('--game')
    parser.add_argument('--data-dir',type=pathlib.Path,default=BASE/'data')
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    from bridge.core import Cache, scan_game, detect_game, export_report, install_pack, atomic_write, dumps
    if args.scan or args.build:
        cache=Cache(args.data_dir)
        scan=scan_game(args.game or detect_game(),cache=cache)
        cache.observe(scan)
        from bridge.scan_cache import save_scan
        save_scan(scan,args.data_dir)
        report=export_report(scan,args.data_dir)
        result={'summary':scan.summary(),'report':str(report)}
        if args.build: result['build']=install_pack(scan,args.data_dir)
        atomic_write(args.data_dir/'last-command.json',dumps(result))
        if sys.stdout: print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    import tkinter as tk
    from bridge.gui import App
    mutex=None
    if os.name=='nt' and not args.self_test:
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p]
        kernel.CreateMutexW.restype=ctypes.c_void_p
        mutex=kernel.CreateMutexW(None,False,'Local\\LimbusAIBridgeDesktopV1')
        if ctypes.get_last_error()==183:
            ctypes.windll.user32.MessageBoxW(0,'边狱补译已经在运行，请使用已打开的窗口。','边狱补译',0)
            return 0
        try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception: pass
    root=tk.Tk()
    if args.self_test: root.withdraw()
    app=App(root,args.data_dir,autostart=not args.self_test)
    if args.self_test:
        root.update_idletasks()
        atomic_write(args.data_dir/'self-test.json',dumps({'ok':True,'title':root.title(),'tabs':len(app.pages),'retranslation_button':hasattr(app,'retranslate_button'),'default_view':app.mode.get(),'max_retries':app.api_vars['retries'].get(),'concurrency':app.api_vars['concurrency'].get(),'tk':root.tk.call('info','patchlevel')}))
        root.destroy(); return 0
    root.mainloop()
    if mutex:
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]; kernel.CloseHandle(mutex)
    return 0

if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as exc:
        # Never print arbitrary provider replies or key-bearing settings.
        if sys.stderr: print(type(exc).__name__+': '+str(exc),file=sys.stderr)
        else:
            ctypes.windll.user32.MessageBoxW(0,'启动或操作失败：'+str(exc),'边狱补译',0x10)
        raise SystemExit(1)
