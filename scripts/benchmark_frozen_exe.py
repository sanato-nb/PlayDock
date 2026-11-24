"""Measure real Windows onefile EXEs without modifying application source or user data."""
from __future__ import annotations
import argparse
import ctypes as c
from ctypes import wintypes as w
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import tempfile
import time

user32=c.WinDLL("user32",use_last_error=True)
kernel32=c.WinDLL("kernel32",use_last_error=True)
CALLBACK=c.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
user32.EnumWindows.argtypes=[CALLBACK,w.LPARAM]
user32.EnumWindows.restype=w.BOOL
user32.IsWindowVisible.argtypes=[w.HWND]
user32.IsWindowVisible.restype=w.BOOL
user32.GetWindowTextW.argtypes=[w.HWND,w.LPWSTR,c.c_int]
user32.GetWindowTextW.restype=c.c_int
user32.GetWindowThreadProcessId.argtypes=[w.HWND,c.POINTER(w.DWORD)]
user32.GetWindowThreadProcessId.restype=w.DWORD
kernel32.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD]
kernel32.OpenProcess.restype=w.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes=[w.HANDLE,w.DWORD,w.LPWSTR,c.POINTER(w.DWORD)]
kernel32.QueryFullProcessImageNameW.restype=w.BOOL
kernel32.CloseHandle.argtypes=[w.HANDLE]
kernel32.CloseHandle.restype=w.BOOL
user32.SendMessageTimeoutW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM,w.UINT,w.UINT,c.POINTER(c.c_size_t)]
user32.SendMessageTimeoutW.restype=w.LPARAM

def main_window(exe):
    target=os.path.normcase(str(exe.resolve()))
    result=[]
    @CALLBACK
    def visit(hwnd,_):
        if not user32.IsWindowVisible(hwnd):
            return True
        title=c.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd,title,len(title))
        if title.value!="PlayDock":
            return True
        pid=w.DWORD()
        user32.GetWindowThreadProcessId(hwnd,c.byref(pid))
        handle=kernel32.OpenProcess(0x1000,False,pid.value)
        if not handle:
            return True
        try:
            path=c.create_unicode_buffer(32768)
            length=w.DWORD(len(path))
            if kernel32.QueryFullProcessImageNameW(handle,0,path,c.byref(length)) and os.path.normcase(path.value)==target:
                reply=c.c_size_t()
                # WM_NULL + SMTO_ABORTIFHUNG: visible and processing messages.
                if user32.SendMessageTimeoutW(hwnd,0,0,0,2,100,c.byref(reply)):
                    result.append(int(hwnd))
                    return False
        finally:
            kernel32.CloseHandle(handle)
        return True
    user32.EnumWindows(visit,0)
    return result[0] if result else None

def stop_tree(process):
    if process.poll() is None:
        subprocess.run(["taskkill","/PID",str(process.pid),"/T","/F"],capture_output=True,timeout=20)
        process.wait(timeout=20)

def measure(exe, count):
    with tempfile.TemporaryDirectory(prefix="playdock-exe-bench-") as tmp:
        root=Path(tmp)
        app=root/"PlayDock.exe"
        shutil.copy2(exe,app)
        data=root/"data";data.mkdir()
        archives=root/"archives";archives.mkdir()
        installed=root/"installed";installed.mkdir()
        for i in range(count):
            (archives/f"Example Game {i:04}.zip").write_bytes(b"synthetic")
        (root/"PlayDock.install.json").write_text(json.dumps({"id":"playdock-installed-v1","data_directory":"data"}),encoding="utf-8")
        (data/"settings.json").write_text(json.dumps({"archives":str(archives),"library":str(installed),"first_run_complete":True}),encoding="utf-8")
        local=root/"localappdata";local.mkdir()
        env={**os.environ,"QT_QPA_PLATFORM":"windows","LOCALAPPDATA":str(local),"QT_SCALE_FACTOR":"1"}
        begin=time.perf_counter()
        process=subprocess.Popen([str(app)],cwd=root,env=env)
        try:
            while time.perf_counter()-begin<90:
                if process.poll() is not None:
                    raise RuntimeError(f"Launcher exited: {process.returncode}")
                if main_window(app):
                    elapsed=(time.perf_counter()-begin)*1000
                    assert (data/"playdock.db").is_file()
                    assert len(list(archives.glob("*.zip")))==count
                    return elapsed
                time.sleep(.05)
            raise RuntimeError("No responsive visible PlayDock window within 90s; interactive Windows desktop required")
        finally:
            stop_tree(process)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--baseline",type=Path,required=True)
    p.add_argument("--optimized",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    paths={"baseline":a.baseline.resolve(),"optimized":a.optimized.resolve()}
    report={"os":platform.platform(),"method":"Popen to visible responsive main HWND; 100 synthetic archives; fresh isolated profile per launch; one warmup and three alternating runs",
            "builds":{},"startup":{}}
    for label,dist in paths.items():
        report["builds"][label]={}
        for name in ("PlayDock.exe","PlayDock_Setup.exe","PlayDock_Uninstall.exe"):
            f=dist/name
            report["builds"][label][name]={"bytes":f.stat().st_size,"sha256":hashlib.file_digest(f.open("rb"),"sha256").hexdigest()}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    def save():
        a.output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    save()
    times={label:[] for label in paths}
    try:
        for label,dist in paths.items():
            measure(dist/"PlayDock.exe",100)
        for i in range(3):
            order=list(paths) if i%2==0 else list(reversed(paths))
            for label in order:
                duration=measure(paths[label]/"PlayDock.exe",100)
                times[label].append(duration)
                print("EXE_STARTUP_SAMPLE",label,duration,flush=True)
                report["startup"]={k:{"samples_ms":v,"median_ms":statistics.median(v)} for k,v in times.items() if v}
                save()
        report["startup_status"]="verified"
        save()
        print("EXE_COMPARISON_VERIFIED",json.dumps(report,ensure_ascii=False))
    except Exception as exc:
        report["startup_status"]="failed"
        report["startup_error"]=str(exc)
        save()
        raise

if __name__=="__main__":
    main()
