@echo off
chcp 65001 >nul
echo ============================================
echo  百度网盘定时下载器 - Windows打包脚本
echo ============================================
echo.

REM 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请先安装Python 3.8+
    pause
    exit /b 1
)

REM 安装依赖
echo [1/3] 安装依赖包...
pip install PyQt5 PyQtWebEngine requests pyinstaller -q
if errorlevel 1 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)
echo 依赖安装完成

REM 清理旧的构建文件
echo [2/3] 清理旧构建...
if exist "dist" rmdir /s /q dist
if exist "build" rmdir /s /q build

REM 执行打包
echo [3/3] 开始打包（这可能需要3-5分钟）...
pyinstaller bdpan.spec --clean

if errorlevel 1 (
    echo.
    echo [错误] 打包失败，请查看上方错误信息
    pause
    exit /b 1
)

echo.
echo ============================================
echo  打包成功！
echo  EXE文件位置: dist\百度网盘定时下载器.exe
echo ============================================
echo.
pause
