import os
import platform
import shutil
import subprocess
import sys
import time

import requests
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QPushButton, QProgressBar, QTextEdit, \
    QMessageBox

# 目录
root_dir = os.getcwd()  # 根目录
temp_dir = os.path.join(root_dir, "temp")  # 临时文件目录
git_dir = os.path.join(root_dir, "lib", "git")

# 路径
git_exe_path = os.path.join(git_dir, "bin","git.exe")  # Git可执行文件路径

# 地址
remote_repo = "https://github.com/baimianxiao/Test_client.git"  # 远程Git仓库（HTTPS）
git_download_urls = [
    "https://registry.npmmirror.com/-/binary/git-for-windows/v2.52.0.windows.1/PortableGit-2.52.0-64-bit.7z.exe",
    "https://gh-proxy.org/https://github.com/git-for-windows/git/releases/download/v2.52.0.windows.1/PortableGit-2.52.0-64-bit.7z.exe",
    "https://github.com/git-for-windows/git/releases/download/v2.52.0.windows.1/PortableGit-2.52.0-64-bit.7z.exe"
]

git_zip_name = "git.7z.exe"  # 下载后的压缩包名

TARGET_UPDATE_DIR = os.getcwd()  # 整合包根目录（即更新目标目录）


# ----------------------------------------------------------------------

class GitDeployThread(QThread):
    """Git便携版自动部署线程（后台执行）"""

    progress_signal = pyqtSignal(int)  # 进度条信号（0-100）
    log_signal = pyqtSignal(str)  # 日志提示信号
    finish_signal = pyqtSignal(bool)  # 部署完成信号（成功/失败）

    def run(self):
        try:
            # 1. 检测Git是否已存在
            if os.path.exists(git_exe_path):
                self.log_signal.emit(f"✅ git.exe已存在，路径:{git_exe_path}")
                self.finish_signal.emit(True)
                return

            # 2. 创建需要的目录
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir)
                self.log_signal.emit(f"🔧 创建Git目录")

            if not os.path.exists(git_dir):
                os.makedirs(git_dir)
                self.log_signal.emit(f"🔧 创建Temp目录")

            # 3. 下载Git便携版
            # 3.1 先测速选最快线路
            fastest_url = self.get_fastest_url(git_download_urls)
            if not fastest_url:
                self.log_signal.emit(f"❌ 所有线路测速失败，尝试全部线路下载...")
                download_urls = git_download_urls
            else:
                self.log_signal.emit(f"✅ 选择最快线路：{fastest_url}")
                download_urls = [fastest_url] + [u for u in git_download_urls if u != fastest_url]

            # 3.2 遍历线路下载（失败自动切换）
            download_success = False
            for idx, url in enumerate(download_urls):
                try:
                    self.log_signal.emit(f"📥 开始从线路 {idx + 1}/{len(download_urls)} 下载：{url}")
                    response = requests.get(url, stream=True, timeout=30,proxies={"http": None, "https": None})
                    response.raise_for_status()  # 触发HTTP错误（如404/500）

                    total_size = int(response.headers.get("content-length", 0))
                    downloaded_size = 0
                    git_zip_path = os.path.join(temp_dir, git_zip_name)
                    with open(git_zip_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                f.write(chunk)
                                downloaded_size += len(chunk)
                                if total_size > 0:
                                    progress = int((downloaded_size / total_size) * 100)
                                    self.progress_signal.emit(progress)
                                    self.log_signal.emit(f"📥 下载进度：{progress}%")

                    # 验证文件完整性（可选但建议保留）
                    if total_size > 0 and downloaded_size != total_size:
                        raise Exception(f"文件大小不匹配：下载{downloaded_size}字节，预期{total_size}字节")

                    self.log_signal.emit(f"✅ Git便携版下载完成！")
                    download_success = True
                    break  # 下载成功，退出线路循环

                except Exception as e:
                    self.log_signal.emit(f"❌ 线路 {url} 下载失败：{str(e)}")
                    # 清理不完整文件
                    if os.path.exists(git_zip_path):
                        os.remove(git_zip_path)
                    # 最后一条线路仍失败
                    if idx == len(download_urls) - 1:
                        self.log_signal.emit(f"❌ 所有线路下载失败！")

            if not download_success:
                raise Exception("Git便携版下载失败，所有线路均不可用")

            # 4. 解压Git压缩包（tar.bz2格式，需先解压外层tar，再取内部Git目录）

            self.log_signal.emit(f"🔧 开始解压{git_zip_name}")
            result = subprocess.run(
                [
                    f"./temp/{git_zip_name}",
                    f"-o./lib/git",  # 解压路径（无空格）
                    "-y",  # 覆盖无需确认
                    "-silent"  # 完全静默（无窗口）
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8",
                shell=False,
                creationflags=subprocess.CREATE_NO_WINDOW  # 隐藏子进程窗口
            )
            self.progress_signal.emit(90)  # 解压阶段固定进度90%
            if result.returncode == 0:
                self.log_signal.emit(f"✅ 解压Git压缩包成功")

            # 5. 验证Git是否可用
            res = subprocess.check_output([git_exe_path, "--version"], shell=False, encoding="utf-8",
                                          stderr=subprocess.STDOUT)
            self.log_signal.emit(f"✅ Git部署成功！版本：{res.strip()}")
            self.progress_signal.emit(100)
            self.finish_signal.emit(True)

        except Exception as e:
            self.log_signal.emit(f"❌ Git部署失败：{str(e)}")
            self.finish_signal.emit(False)

    # 测速函数：返回最快地下载地址
    def get_fastest_url(self, url_list, timeout=5):
        fastest_url = None
        min_response_time = float("inf")
        for url in url_list:
            try:
                self.log_signal.emit(f"🔍 测试线路：{url}")
                start_time = time.time()
                # 仅发送HEAD请求测速（不下载内容）
                response = requests.head(url, timeout=timeout, allow_redirects=True)
                if response.status_code == 200:
                    response_time = time.time() - start_time
                    self.log_signal.emit(f"📶 线路 {url} 响应时间：{response_time:.2f}秒")
                    if response_time < min_response_time:
                        min_response_time = response_time
                        fastest_url = url
            except Exception as e:
                self.log_signal.emit(f"❌ 线路 {url} 测速失败：{str(e)}")
                continue
        return fastest_url


class UpdateThread(QThread):
    """整合包更新线程（后台执行）"""
    log_signal = pyqtSignal(str)
    finish_signal = pyqtSignal(bool)

    def get_local_tag(self):
        """获取本地当前版本Tag"""
        try:
            res = subprocess.check_output(
                [git_exe_path, "describe", "--tags", "--abbrev=0"],
                cwd=TARGET_UPDATE_DIR, shell=False, encoding="utf-8", stderr=subprocess.STDOUT
            )
            return res.strip()
        except:
            return "未初始化（首次使用）"

    def get_remote_tag(self):
        """获取远程最新Tag"""
        try:
            # 拉取远程Tag列表并排序
            res = subprocess.check_output(
                [git_exe_path, "ls-remote", "--tags", "--sort=-v:refname", remote_repo],
                cwd=TARGET_UPDATE_DIR, shell=False, encoding="utf-8", stderr=subprocess.STDOUT
            )
            latest_tag = res.split("\n")[0].split("/")[-1].strip()
            return latest_tag
        except Exception as e:
            self.log_signal.emit(f"❌ 拉取远程版本失败：{str(e)}")
            return None

    def run(self):
        try:
            # 1. 初始化Git仓库（首次使用）
            if not os.path.exists(os.path.join(TARGET_UPDATE_DIR, ".git")):
                self.log_signal.emit("🔧 首次更新，初始化本地仓库...")
                subprocess.check_call(
                    [git_exe_path, "init"], cwd=TARGET_UPDATE_DIR, shell=False, stderr=subprocess.STDOUT
                )
                subprocess.check_call(
                    [git_exe_path, "remote", "add", "origin", remote_repo],
                    cwd=TARGET_UPDATE_DIR, shell=False, stderr=subprocess.STDOUT
                )

            # 2. 拉取远程信息
            self.log_signal.emit("📥 拉取远程最新版本信息...")
            subprocess.check_call(
                [git_exe_path, "fetch", "origin", "--tags"],
                cwd=TARGET_UPDATE_DIR, shell=False, stderr=subprocess.STDOUT
            )

            # 3. 版本对比
            local_tag = self.get_local_tag()
            remote_tag = self.get_remote_tag()
            if not remote_tag:
                self.finish_signal.emit(False)
                return

            self.log_signal.emit(f"📌 本地版本：{local_tag}")
            self.log_signal.emit(f"📌 远程版本：{remote_tag}")
            if local_tag == remote_tag:
                self.log_signal.emit("✅ 当前已是最新版本，无需更新！")
                self.finish_signal.emit(True)
                return

            # 4. 执行增量更新（强制切换Tag，忽略本地修改；需保留配置可改merge）
            self.log_signal.emit(f"🔄 开始更新到版本：{remote_tag}...")
            subprocess.check_call(
                [git_exe_path, "checkout", "-f", remote_tag],
                cwd=TARGET_UPDATE_DIR, shell=False, stderr=subprocess.STDOUT
            )
            self.log_signal.emit(f"✅ 更新完成！当前版本：{remote_tag}")
            self.finish_signal.emit(True)

        except Exception as e:
            self.log_signal.emit(f"❌ 更新失败：{str(e)}")
            self.finish_signal.emit(False)


class MCUpdaterGUI(QWidget):
    """整合包更新器GUI界面"""

    def __init__(self):
        super().__init__()
        self.init_ui()
        self.git_deployed = False  # Git是否部署完成标记

    def init_ui(self):
        # 窗口配置
        self.setWindowTitle("MC整合包自动更新器 v1.0")
        self.setFixedSize(500, 400)  # 固定窗口大小，避免拉伸变形
        self.setStyleSheet("""
            QWidget { background-color: #2c3e50; color: #ecf0f1; font-size: 14px; }
            QPushButton { background-color: #3498db; color: white; border: none; padding: 10px; border-radius: 5px; }
            QPushButton:hover { background-color: #2980b9; }
            QPushButton:disabled { background-color: #7f8c8d; }
            QProgressBar { height: 15px; border-radius: 7px; background-color: #34495e; }
            QProgressBar::chunk { background-color: #2ecc71; border-radius: 7px; }
            QTextEdit { background-color: #34495e; border: none; padding: 10px; border-radius: 5px; }
            QLabel { font-size: 16px; font-weight: bold; margin-bottom: 10px; }
        """)

        # 布局管理
        layout = QVBoxLayout()
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # 标题标签
        title_label = QLabel("MC整合包更新器")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # 日志显示框（不可编辑，显示部署/更新进度）
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        layout.addWidget(self.log_edit)

        # 进度条（仅Git部署时显示进度，更新时隐藏）
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setVisible(False)  # 初始隐藏
        layout.addWidget(self.progress_bar)

        # 更新按钮
        self.update_btn = QPushButton("检测并更新")
        self.update_btn.clicked.connect(self.start_update_flow)
        layout.addWidget(self.update_btn)

        self.setLayout(layout)

    def log_print(self, msg):
        """日志显示（追加到文本框，自动滚动到底部）"""
        self.log_edit.append(msg)
        self.log_edit.verticalScrollBar().setValue(self.log_edit.verticalScrollBar().maximum())

    def start_update_flow(self):
        """启动更新流程：先部署Git → 再执行更新"""
        self.update_btn.setEnabled(False)
        self.log_edit.clear()
        self.log_print("===== 开始更新流程 =====")

        # 1. 启动Git部署线程
        self.git_thread = GitDeployThread()
        self.git_thread.progress_signal.connect(self.update_progress)
        self.git_thread.log_signal.connect(self.log_print)
        self.git_thread.finish_signal.connect(self.on_git_deploy_finish)
        self.git_thread.start()

    def update_progress(self, value):
        """更新进度条（显示并设置值）"""
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(value)

    def on_git_deploy_finish(self, success):
        """Git部署完成后的回调"""
        if not success:
            self.update_btn.setEnabled(True)
            QMessageBox.warning(self, "错误", "Git部署失败，请检查网络连接后重试！")
            return

        self.git_deployed = True
        self.progress_bar.setVisible(False)  # 隐藏进度条
        self.log_print("===== Git部署完成，开始检测更新 =====")

        # 2. 启动更新线程
        self.update_thread = UpdateThread()
        self.update_thread.log_signal.connect(self.log_print)
        self.update_thread.finish_signal.connect(self.on_update_finish)
        self.update_thread.start()

    def on_update_finish(self, success):
        """更新完成后的回调"""
        self.update_btn.setEnabled(True)
        if success:
            QMessageBox.information(self, "成功", "更新流程结束！可关闭窗口启动游戏~")
        else:
            QMessageBox.warning(self, "错误", "更新失败，请查看日志排查问题！")


if __name__ == "__main__":
    # 适配Windows高分屏（避免界面模糊）
    if platform.system() == "Windows":
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)

    app = QApplication(sys.argv)
    gui = MCUpdaterGUI()
    gui.show()
    sys.exit(app.exec_())
