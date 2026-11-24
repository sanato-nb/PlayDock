"""Start a real frozen launcher in temporary isolated data, without installing."""
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

exe=Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory(prefix="playdock-frozen-smoke-") as folder:
    root=Path(folder)
    copied=root/"PlayDock.exe"
    shutil.copy2(exe,copied)
    data=root/"data";data.mkdir()
    archives=root/"archives";archives.mkdir()
    installed=root/"installed";installed.mkdir()
    (archives/"Example.zip").write_bytes(b"synthetic")
    (root/"PlayDock.install.json").write_text(json.dumps({"id":"playdock-installed-v1","data_directory":"data"}),encoding="utf-8")
    (data/"settings.json").write_text(json.dumps({"archives":str(archives),"library":str(installed),"first_run_complete":True}),encoding="utf-8")
    env={**os.environ,"QT_QPA_PLATFORM":"offscreen","LOCALAPPDATA":str(root/"localappdata")}
    start=time.monotonic()
    process=subprocess.Popen([str(copied)],cwd=root,env=env)
    try:
        while time.monotonic()-start<90:
            if process.poll() is not None:
                raise RuntimeError(f"Launcher exited: {process.returncode}")
            if (data/"playdock.db").is_file():
                try:
                    with closing(sqlite3.connect(data/"playdock.db")) as conn:
                        ready=conn.execute("PRAGMA user_version").fetchone()[0]==3
                    if ready:
                        break
                except sqlite3.Error:
                    pass
            time.sleep(.2)
        else:
            raise RuntimeError("Frozen launcher did not initialize isolated DB")
        time.sleep(3)
        assert process.poll() is None, "Launcher exited after DB initialization"
        assert (archives/"Example.zip").read_bytes()==b"synthetic"
        print("FROZEN_LAUNCHER_DB_INITIALIZED_AND_RUNNING")
    finally:
        if process.poll() is None:
            subprocess.run(["taskkill","/PID",str(process.pid),"/T","/F"],capture_output=True)
            process.wait(timeout=20)
