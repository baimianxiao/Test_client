import pathlib
import zipfile
import json
import toml
from pathlib import Path


def get_mcmod_version(mod_path: str) -> dict:
    """
    读取MC Mod的版本号
    :param mod_path: Mod文件路径（.jar）
    :return: 字典，key为modid，value为版本号（支持单个JAR内多个Mod）
    """
    version_info = {}
    mod_path = Path(mod_path)

    # 校验文件合法性
    if not mod_path.exists() or mod_path.suffix != ".jar":
        raise ValueError("无效的Mod文件路径（需为.jar文件）")

    # 读取JAR包内的配置文件
    with zipfile.ZipFile(mod_path, "r") as jar_file:

        if "META-INF/neoforge.mods.toml" in jar_file.namelist():
            with jar_file.open("META-INF/neoforge.mods.toml") as f:
                # 读取toml（处理编码问题）
                toml_content = f.read().decode("utf-8", errors="ignore")
                mod_data = toml.loads(toml_content)
                # 单Mod场景
                result = {}
                if "mods" in mod_data:
                    for mod in mod_data["mods"]:
                        if "modId" in mod and "version" in mod:
                            result["modId"] = mod["modId"]
                            result["version"] = mod["version"]
                            result["displayName"] = mod["displayName"]
                return result

    # 无匹配配置文件
    raise RuntimeError("未找到Mod版本配置文件（非标准Forge/Fabric/Quilt Mod）")


# 示例调用
if __name__ == "__main__":
    # 替换为你的Mod文件路径
    mod_jar_path = ".minecraft/versions/CMagic_client/mods/[1.21.1] SecurityCraft v1.10.1.jar"
    mod_dir= pathlib.Path(".minecraft/versions/CMagic_client/mods/")
    for file_path in mod_dir.iterdir():
        try:
            if file_path.suffix == ".jar":
                mod_data = get_mcmod_version(file_path)
                modid, version ,displayName= mod_data["modId"], mod_data["version"], mod_data["displayName"]
                print(f"ModID: {modid}, 版本号: {version}", f"Mod名称: {displayName}")
        except Exception as e:
            print(f"读取{file_path.name} Mod版本信息时出错: {e}")

