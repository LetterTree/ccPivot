@echo off
chcp 65001 >nul
echo 正在安装依赖...
pip install toml ttkbootstrap
echo.
echo 依赖安装完成！
echo 现在可以运行 启动.bat 启动程序
pause
