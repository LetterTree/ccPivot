@echo off
chcp 65001 >nul
echo 正在安装依赖...
pip install toml ttkbootstrap
echo.
echo 依赖安装完成！
echo 现在可以双击 ccPivot.exe 启动程序
pause
