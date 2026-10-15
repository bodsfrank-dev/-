@echo off
chcp 65001 >nul
REM ============================================================
REM  久坐提醒 —— 构建 Windows 独立 exe
REM  本脚本在【装有 Python 的 Windows 电脑】上运行，
REM  用于把源码打包成「双击即用、无需安装 Python」的 exe。
REM  若你手上没有 Windows/Python 环境，请改用 GitHub Actions，
REM  详见本文件夹内的 README.md（无需本机环境即可出包）。
REM ============================================================
setlocal

REM 优先用 py 启动器，否则用 python
where py >nul 2>nul && set PY=py
if not defined PY ( set "PY=python" )

echo.
echo [1/3] 安装/升级构建依赖（仅用于本机打包，不影响最终 exe）...
%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements_build.txt

echo.
echo [2/3] 使用 PyInstaller 打包为单文件 exe（--onefile --windowed）...
%PY% -m PyInstaller 久坐提醒.spec --noconfirm --clean

echo.
echo [3/3] 完成。产物位于： dist\久坐提醒.exe
echo 把它拷到任意 Windows 电脑双击即可运行，目标机器无需安装 Python。
echo.
pause
