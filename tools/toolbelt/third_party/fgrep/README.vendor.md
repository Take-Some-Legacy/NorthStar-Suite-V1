# GNU fgrep compatibility wrapper

MSYS2 no longer ships a separate `fgrep.exe` in this environment, so this package uses vendored `grep.exe` with a thin `fgrep.bat` wrapper that executes `grep -F`.

