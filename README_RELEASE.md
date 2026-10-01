# Android Device Manager V5.3 — Release Packaging

## macOS / Linux

Double-click:

`AndroidDeviceManager.command`

or from a terminal:

```bash
chmod +x AndroidDeviceManager.command
./AndroidDeviceManager.command
```

The launcher looks for `python3` first and then `python`.

## Windows

A Windows `.exe` should be built on Windows so PyInstaller produces a native Windows executable.

1. Put these files in the same folder:
   - `android_device_manager_v5_3.py`
   - `build_windows_exe.bat`

2. Double-click `build_windows_exe.bat`.

3. The finished executable will be:

`dist/AndroidDeviceManager_V5.3.exe`

The build uses PyInstaller's `--onefile --windowed` mode.

## Android platform tools

The application still requires the Android command-line tools to be available on the host system:

- `adb`
- `fastboot`
- optionally `heimdall`

The Python application does not bundle Android platform tools.

## Important release note

The Windows `.exe` cannot reliably be produced as a native Windows executable from this Linux environment. The included Windows builder is the correct reproducible way to generate the EXE on Windows.

## Suggested GitHub release files

- `android_device_manager_v5_3.py`
- `AndroidDeviceManager.command`
- `build_windows_exe.bat`
- `build_unix.sh`
- `README_RELEASE.md`
