@echo off
chcp 65001 >nul
echo =====================================
echo   ccPivot 开发环境依赖安装
echo   （仅从源码运行时需要）
echo =====================================
echo.
echo 正在安装依赖...
pip install toml ttkbootstrap
echo.
echo 依赖安装完成！
echo 现在可以执行 python config_switcher.py 启动程序
echo （普通用户直接双击 ccPivot.exe 即可）
pause
