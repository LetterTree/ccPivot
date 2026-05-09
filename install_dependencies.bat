@echo off
chcp 65001 >nul
echo 正在安装依赖...
pip install toml
echo.
echo 依赖安装完成！
echo 现在可以运行 run_config_switcher.bat 启动程序
pause
