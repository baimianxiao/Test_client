import os
import json
import hashlib
import math
from datetime import datetime
import argparse

root_dir = os.getcwd()  # 根目录
config_dir = os.path.join(root_dir, "config")
# 单位转换常量（1MB = 1024*1024 字节）
MB_TO_BYTES = 1024 * 1024
# 分割阈值：100MB
SPLIT_THRESHOLD = 50 * MB_TO_BYTES
# 分包大小：40MB
CHUNK_SIZE = 30 * MB_TO_BYTES


def calculate_file_hash(file_path, hash_algorithm="md5"):
    """
    计算文件的哈希值，用于验证文件完整性
    :param file_path: 文件路径
    :param hash_algorithm: 哈希算法（默认md5）
    :return: 文件的哈希值字符串
    """
    try:
        hash_obj = hashlib.new(hash_algorithm)
        with open(file_path, 'rb') as f:
            # 分块读取文件，避免大文件占用过多内存
            while chunk := f.read(4096):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()
    except Exception as e:
        print(f"计算文件 {file_path} 哈希失败: {e}")
        return None


def split_large_file(file_path, output_dir=None):
    """
    分割大文件为指定大小的分包，并返回分包信息
    :param file_path: 原文件路径
    :param output_dir: 分包输出目录（默认和原文件同目录）
    :return: 分包信息字典，包含分包路径列表、每个分包的哈希等
    """
    if output_dir is None:
        output_dir = os.path.dirname(file_path)
    os.makedirs(output_dir, exist_ok=True)

    # 获取文件基本信息
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)

    # 计算需要分割的分包数量
    chunk_count = math.ceil(file_size / CHUNK_SIZE)
    chunk_info_list = []

    print(f"开始分割文件: {file_path} (大小: {file_size / MB_TO_BYTES:.2f}MB)，将分割为 {chunk_count} 个分包")

    try:
        with open(file_path, 'rb') as src_file:
            for chunk_idx in range(chunk_count):
                # 分包命名规则：原文件名.part{序号}（序号从1开始）
                chunk_file_name = f"{file_name}.part{chunk_idx + 1:02d}"
                chunk_file_path = os.path.join(output_dir, chunk_file_name)

                # 读取并写入分包数据
                with open(chunk_file_path, 'wb') as chunk_file:
                    # 读取指定大小的内容（最后一个分包可能小于40MB）
                    chunk_data = src_file.read(CHUNK_SIZE)
                    chunk_file.write(chunk_data)

                # 计算分包的哈希和大小
                chunk_size = os.path.getsize(chunk_file_path)
                chunk_hash = calculate_file_hash(chunk_file_path)

                chunk_info = {
                    "chunk_name": chunk_file_name,
                    "chunk_path": chunk_file_path,
                    "chunk_size_bytes": chunk_size,
                    "chunk_size_mb": round(chunk_size / MB_TO_BYTES, 2),
                    "chunk_hash": chunk_hash,
                    "chunk_index": chunk_idx + 1
                }
                chunk_info_list.append(chunk_info)

                print(f"  生成分包: {chunk_file_name} (大小: {chunk_size / MB_TO_BYTES:.2f}MB, 哈希: {chunk_hash})")

        return {
            "original_file_size_bytes": file_size,
            "original_file_size_mb": round(file_size / MB_TO_BYTES, 2),
            "original_file_hash": calculate_file_hash(file_path),
            "chunk_count": chunk_count,
            "chunk_size_setting_mb": 30,
            "chunks": chunk_info_list
        }
    except Exception as e:
        print(f"分割文件 {file_path} 失败: {e}")
        # 清理已生成的分包
        for chunk_info in chunk_info_list:
            if os.path.exists(chunk_info["chunk_path"]):
                os.remove(chunk_info["chunk_path"])
        return None


def main(mod_dir, config_file_name="mod_info.json"):
    """
    主函数：遍历Mod目录，分割大文件并生成包含所有Mod文件校验信息的配置文件
    :param mod_dir: Mod目录路径
    :param config_file_name: 生成的配置文件名
    """
    # 验证目录是否存在
    if not os.path.isdir(mod_dir):
        print(f"错误：目录 {mod_dir} 不存在！")
        return

    # 配置文件的整体结构（调整为包含所有Mod文件）
    split_config = {
        "split_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "split_threshold_mb": 50,
        "chunk_size_mb": 30,
        "mod_directory": mod_dir,
        "all_mod_files": []  # 替换原split_files，存储所有Mod文件的校验信息
    }

    # 遍历Mod目录下的所有文件
    for root, dirs, files in os.walk(mod_dir):
        for file in files:
            if not file.lower().endswith('.jar'):
                 continue
            file_path = os.path.join(root, file)
            file_size = os.path.getsize(file_path)
            file_hash = calculate_file_hash(file_path)

            # 初始化单个文件的基础信息（所有文件都包含）
            file_info = {
                "file_path": file_path,
                "file_name": file,
                "file_size_bytes": file_size,
                "file_size_mb": round(file_size / MB_TO_BYTES, 2),
                "file_hash": file_hash,
                "is_split": False  # 默认未分割
            }

            # 筛选大于100MB的文件，执行分割并补充分包信息
            if file_size > SPLIT_THRESHOLD:
                # 分割文件
                split_info = split_large_file(file_path)
                if split_info:
                    # 补充分割相关信息
                    file_info["is_split"] = True
                    file_info["split_details"] = split_info
                print(f"文件 {file_path} (大小: {file_size / MB_TO_BYTES:.2f}MB) 已分割并记录校验信息")
            else:
                print(f"文件 {file_path} (大小: {file_size / MB_TO_BYTES:.2f}MB) 无需分割，仅记录校验信息")

            # 将当前文件信息加入配置（无论是否分割）
            split_config["all_mod_files"].append(file_info)

    # 生成JSON配置文件
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)
    config_file_path = os.path.join(config_dir, config_file_name)
    try:
        with open(config_file_path, 'w', encoding='utf-8') as f:
            # 格式化输出JSON，便于阅读
            json.dump(split_config, f, ensure_ascii=False, indent=4)
        print(f"\n配置文件已生成：{config_file_path}")
        print(f"配置文件包含 {len(split_config['all_mod_files'])} 个Mod文件的校验信息")
    except Exception as e:
        print(f"生成配置文件失败: {e}")




if __name__ == "__main__":
    # 使用argparse支持命令行参数
    parser = argparse.ArgumentParser(description="MC Mod大文件分割工具 - 将大于100MB的Mod分割为40MB分包，并生成验证配置文件")
    # parser.add_argument("--mod-dir", required=True, help="MC Mod目录的绝对/相对路径")
    # parser.add_argument("--config-name", default="mod_split_config.json", help="生成的配置文件名（默认：mod_split_config.json）")
    # args = parser.parse_args()

    # 执行主函数
    # main(args.mod_dir, args.config_name)
    main(".minecraft/versions/CMagic_client/mods")