import os
import json
import hashlib
import argparse
from pathlib import Path

# 单位转换常量（仅用于展示，校验用字节数）
BYTES_TO_MB = 1024 * 1024

# ===================== 核心工具函数 =====================
def calculate_file_hash(file_path, hash_algorithm="md5"):
    """
    计算文件哈希值（分块读取，避免大文件内存溢出）
    :param file_path: 本地文件路径
    :param hash_algorithm: 哈希算法（与配置文件保持一致，默认MD5）
    :return: 哈希字符串（失败返回None）
    """
    if not os.path.exists(file_path):
        return None
    try:
        hash_obj = hashlib.new(hash_algorithm)
        with open(file_path, 'rb') as f:
            while chunk := f.read(4096):  # 4096字节/块，平衡效率与内存
                hash_obj.update(chunk)
        return hash_obj.hexdigest()
    except Exception as e:
        print(f"[警告] 计算 {os.path.basename(file_path)} 哈希失败：{str(e)}")
        return None

def get_file_size_bytes(file_path):
    """
    获取本地文件精准字节数
    :param file_path: 本地文件路径
    :return: 字节数（失败返回None）
    """
    if not os.path.exists(file_path):
        return None
    try:
        return os.path.getsize(file_path)
    except Exception as e:
        print(f"[警告] 获取 {os.path.basename(file_path)} 大小失败：{str(e)}")
        return None

def get_local_mod_file_map(local_mod_dir):
    """
    获取本地Mod目录的文件映射表（哈希->文件信息，文件名->文件信息）
    用于快速匹配「哈希一致文件名不同」的情况
    :param local_mod_dir: 本地Mod目录
    :return: hash_to_files（哈希为键，值为文件信息列表）、name_to_files（文件名为键，值为文件信息）、all_local_files（所有本地文件信息列表）
    """
    hash_to_files = {}
    name_to_files = {}
    all_local_files = []

    if not os.path.isdir(local_mod_dir):
        return hash_to_files, name_to_files, all_local_files

    # 遍历本地Mod目录所有文件
    for root, dirs, files in os.walk(local_mod_dir):
        for file in files:
            file_path = os.path.join(root, file)
            file_hash = calculate_file_hash(file_path)
            file_size = get_file_size_bytes(file_path)

            # 构造文件信息
            file_info = {
                "file_name": file,
                "file_path": file_path,
                "hash": file_hash,
                "size_bytes": file_size,
                "size_mb": round(file_size / BYTES_TO_MB, 4) if file_size else None
            }
            all_local_files.append(file_info)

            # 加入哈希映射（一个哈希可能对应多个文件）
            if file_hash:
                if file_hash not in hash_to_files:
                    hash_to_files[file_hash] = []
                hash_to_files[file_hash].append(file_info)

            # 加入文件名映射
            if file not in name_to_files:
                name_to_files[file] = []
            name_to_files[file].append(file_info)

    return hash_to_files, name_to_files, all_local_files

# ===================== 核心校验逻辑 =====================
def validate_mods_with_config(config_file_path, local_mod_dir=None):
    """
    使用JSON配置文件校验本地Mod，忽略哈希一致文件名不同的情况，列出多出文件，缺失文件补充is_split和split_details
    :param config_file_path: JSON配置文件路径
    :param local_mod_dir: 本地Mod目录（可选，若不指定则使用配置文件中记录的目录）
    :return: inconsistent_mods（不一致项）、extra_local_files（本地多出文件）
    """
    # 1. 验证配置文件是否存在
    if not os.path.isfile(config_file_path):
        print(f"[错误] 配置文件不存在：{config_file_path}")
        return {}, []

    # 2. 读取JSON配置文件
    try:
        with open(config_file_path, 'r', encoding='utf-8') as f:
            mod_config = json.load(f)
        print(f"[成功] 读取配置文件：{os.path.basename(config_file_path)}")
        print(f"[信息] 配置文件生成时间：{mod_config['split_time']}")
        print(f"[信息] 配置文件记录Mod总数：{len(mod_config['all_mod_files'])}")
    except Exception as e:
        print(f"[错误] 解析配置文件失败：{str(e)}")
        return {}, []

    # 3. 确定本地Mod目录
    if not local_mod_dir:
        local_mod_dir = mod_config['mod_directory']
        print(f"[信息] 使用配置文件中记录的Mod目录：{local_mod_dir}")
    if not os.path.isdir(local_mod_dir):
        print(f"[错误] 本地Mod目录不存在：{local_mod_dir}")
        return {}, []

    # 4. 获取本地Mod文件映射表
    local_hash_map, local_name_map, all_local_files = get_local_mod_file_map(local_mod_dir)
    print(f"[信息] 本地Mod目录文件总数：{len(all_local_files)}")

    # 5. 提取配置文件中的Mod信息（哈希集合、文件名集合）
    config_hash_set = set()
    config_name_set = set()
    config_mod_list = []
    for mod_info in mod_config['all_mod_files']:
        mod_hash = mod_info['file_hash']
        mod_name = mod_info['file_name']
        if mod_hash:
            config_hash_set.add(mod_hash)
        config_name_set.add(mod_name)
        config_mod_list.append(mod_info)

    # 6. 初始化不一致信息列表（分类存储）
    inconsistent_mods = {
        "missing_files": [],  # 文件缺失（哈希和文件名均无匹配）
        "size_mismatch": [],  # 大小不匹配（哈希未匹配，文件名匹配但大小不一致）
        "hash_mismatch": [],  # 哈希不匹配（文件名匹配，但哈希不一致）
        "error_files": []     # 读取/计算异常的文件
    }

    # 7. 遍历配置文件中的所有Mod，逐一校验（忽略哈希一致文件名不同）
    for idx, mod_info in enumerate(config_mod_list, 1):
        mod_file_name = mod_info['file_name']
        mod_config_path = mod_info['file_path']
        mod_expected_size = mod_info['file_size_bytes']
        mod_expected_hash = mod_info['file_hash']
        # 提取is_split和split_details字段（兼容无此字段的情况，用get默认值）
        mod_is_split = mod_info.get("is_split", False)
        mod_split_details = mod_info.get("split_details", None)

        print(f"\n[{idx}/{len(config_mod_list)}] 校验：{mod_file_name}（预期哈希：{mod_expected_hash[:8]}...）")

        # ---- 步骤1：先通过哈希匹配（忽略文件名差异） ----
        hash_matched = False
        if mod_expected_hash and mod_expected_hash in local_hash_map:
            # 找到哈希匹配的本地文件，视为内容一致，忽略文件名差异
            matched_local_files = local_hash_map[mod_expected_hash]
            hash_matched = True
            print(f"  [匹配] 哈希一致（内容相同），忽略文件名差异，匹配到本地文件：{[f['file_name'] for f in matched_local_files]}")
            continue  # 哈希匹配，无需后续校验，直接跳过

        # ---- 步骤2：哈希未匹配，按文件名匹配校验 ----
        if mod_file_name not in local_name_map:
            # 文件名也未匹配，视为文件缺失，补充is_split和split_details
            inconsistent_mods['missing_files'].append({
                "file_name": mod_file_name,
                "config_path": mod_config_path,
                "expected_hash": mod_expected_hash,
                "is_split": mod_is_split,  # 新增：是否为分割文件
                "split_details": mod_split_details,  # 新增：分割详情
                "reason": "本地无哈希匹配文件，且文件名不存在"
            })
            print(f"  [缺失] 本地无哈希匹配文件，且未找到文件名 {mod_file_name}")
            continue

        # ---- 步骤3：文件名匹配，校验大小 ----
        local_mod_files = local_name_map[mod_file_name]
        local_mod_file = local_mod_files[0]  # 取第一个同名文件
        local_mod_path = local_mod_file['file_path']
        local_mod_size = local_mod_file['size_bytes']
        local_mod_hash = local_mod_file['hash']

        # 校验文件大小
        if local_mod_size is None:
            inconsistent_mods['error_files'].append({
                "file_name": mod_file_name,
                "local_path": local_mod_path,
                "reason": "无法获取本地文件大小"
            })
            print(f"  [异常] 无法获取同名文件 {mod_file_name} 大小")
            continue
        if local_mod_size != mod_expected_size:
            inconsistent_mods['size_mismatch'].append({
                "file_name": mod_file_name,
                "local_path": local_mod_path,
                "expected_size_bytes": mod_expected_size,
                "expected_size_mb": round(mod_expected_size / BYTES_TO_MB, 4),
                "actual_size_bytes": local_mod_size,
                "actual_size_mb": local_mod_file['size_mb'],
                "reason": "文件名匹配，但大小不一致"
            })
            print(f"  [不匹配] 大小不一致（预期：{round(mod_expected_size/BYTES_TO_MB,4)}MB，实际：{local_mod_file['size_mb']}MB）")
        else:
            print(f"  [匹配] 大小一致：{local_mod_file['size_mb']}MB")

        # ---- 步骤4：文件名匹配，校验哈希 ----
        if local_mod_hash is None:
            inconsistent_mods['error_files'].append({
                "file_name": mod_file_name,
                "local_path": local_mod_path,
                "reason": "无法计算本地文件哈希"
            })
            print(f"  [异常] 无法计算同名文件 {mod_file_name} 哈希")
            continue
        if local_mod_hash != mod_expected_hash:
            inconsistent_mods['hash_mismatch'].append({
                "file_name": mod_file_name,
                "local_path": local_mod_path,
                "expected_hash": mod_expected_hash,
                "actual_hash": local_mod_hash,
                "reason": "文件名匹配，但哈希不一致（内容被修改或损坏）"
            })
            print(f"  [不匹配] 哈希不一致（预期：{mod_expected_hash[:8]}...，实际：{local_mod_hash[:8]}...）")
        else:
            print(f"  [匹配] 哈希一致：{local_mod_hash[:8]}...")

    # 8. 筛选本地多出的文件（配置中无哈希匹配，且无文件名匹配）
    extra_local_files = []
    for local_file in all_local_files:
        local_file_hash = local_file['hash']
        local_file_name = local_file['file_name']

        # 配置中存在该哈希 或 存在该文件名，不视为多出文件
        if (local_file_hash in config_hash_set) or (local_file_name in config_name_set):
            continue

        if not local_file_name.endswith(".jar"):
            continue

        # 配置中无哈希和文件名匹配，视为多出文件
        extra_local_files.append({
            "file_name": local_file_name,
            "file_path": local_file['file_path'],
            "hash": local_file_hash,
            "size_mb": local_file['size_mb'],
            "reason": "配置文件中未记录该文件（无哈希/文件名匹配）"
        })

    return inconsistent_mods, extra_local_files

# ===================== 输出校验报告 =====================
def print_validate_report(inconsistent_mods, extra_local_files):
    """
    格式化输出校验报告，包含不一致项和本地多出文件，缺失文件展示is_split和split_details
    :param inconsistent_mods: 不一致Mod信息字典
    :param extra_local_files: 本地多出文件列表
    """
    print(f"\n" + "="*80)
    print(f"                      Mod校验报告")
    print(f"="*80)

    # 统计总不一致数
    total_inconsistent = (len(inconsistent_mods['missing_files']) +
                          len(inconsistent_mods['size_mismatch']) +
                          len(inconsistent_mods['hash_mismatch']) +
                          len(inconsistent_mods['error_files']))

    # 输出不一致项
    if total_inconsistent > 0:
        print(f"\n[警告] 共发现 {total_inconsistent} 个不一致/异常项，详情如下：")

        # 1. 输出文件缺失列表（展示is_split和split_details）
        if inconsistent_mods['missing_files']:
            print(f"\n--- 1. 本地文件缺失（{len(inconsistent_mods['missing_files'])} 个） ---")
            for idx, mod in enumerate(inconsistent_mods['missing_files'], 1):
                print(f"  {idx}. 文件名：{mod['file_name']}")
                print(f"     配置路径：{mod['config_path']}")
                print(f"     预期哈希：{mod['expected_hash']}")
                print(f"     是否为分割文件：{mod['is_split']}")
                # 展示split_details（若存在）
                if mod['split_details']:
                    print(f"     分割详情：")
                    # 简化展示split_details核心信息（避免输出过长）
                    split_chunk_count = mod['split_details'].get('chunk_count', 0)
                    split_original_size = mod['split_details'].get('original_file_size_mb', 0)
                    print(f"       - 分包数量：{split_chunk_count}")
                    print(f"       - 原文件大小：{split_original_size} MB")
                    print(f"       - 分包配置：存在（可用于后续合成）")
                else:
                    print(f"     分割详情：无（非分割文件）")
                print(f"     缺失原因：{mod['reason']}")

        # 2. 输出大小不匹配列表
        if inconsistent_mods['size_mismatch']:
            print(f"\n--- 2. 文件大小不匹配（{len(inconsistent_mods['size_mismatch'])} 个） ---")
            for idx, mod in enumerate(inconsistent_mods['size_mismatch'], 1):
                print(f"  {idx}. 文件名：{mod['file_name']}")
                print(f"     本地路径：{mod['local_path']}")
                print(f"     预期大小：{mod['expected_size_mb']} MB（{mod['expected_size_bytes']} 字节）")
                print(f"     实际大小：{mod['actual_size_mb']} MB（{mod['actual_size_bytes']} 字节）")

        # 3. 输出哈希不匹配列表
        if inconsistent_mods['hash_mismatch']:
            print(f"\n--- 3. 文件哈希不匹配（内容异常，{len(inconsistent_mods['hash_mismatch'])} 个） ---")
            for idx, mod in enumerate(inconsistent_mods['hash_mismatch'], 1):
                print(f"  {idx}. 文件名：{mod['file_name']}")
                print(f"     本地路径：{mod['local_path']}")
                print(f"     预期哈希：{mod['expected_hash']}")
                print(f"     实际哈希：{mod['actual_hash']}")

        # 4. 输出异常文件列表
        if inconsistent_mods['error_files']:
            print(f"\n--- 4. 文件读取/计算异常（{len(inconsistent_mods['error_files'])} 个） ---")
            for idx, mod in enumerate(inconsistent_mods['error_files'], 1):
                print(f"  {idx}. 文件名：{mod['file_name']}")
                print(f"     本地路径：{mod['local_path']}")
                print(f"     异常原因：{mod['reason']}")
    else:
        print(f"\n[恭喜] 所有配置内Mod校验通过，无不一致项！")

    # 输出本地多出文件
    if extra_local_files:
        print(f"\n--- 5. 本地多出文件（配置未记录，{len(extra_local_files)} 个） ---")
        for idx, file in enumerate(extra_local_files, 1):
            print(f"  {idx}. 文件名：{file['file_name']}")
            print(f"     本地路径：{file['file_path']}")
            print(f"     文件大小：{file['size_mb']} MB")
            print(f"     文件哈希：{file['hash'] if file['hash'] else '无法计算'}")
    else:
        print(f"\n[信息] 本地无多出Mod，所有文件均在配置记录中")

    print(f"\n" + "="*80)


# ===================== 主函数 =====================
def main():


    # 执行校验
    inconsistent_mods, extra_local_files = validate_mods_with_config("temp/latest_mod_info.json", ".minecraft/versions/CMagic_client/mods")
    print(inconsistent_mods)
    print(extra_local_files)
    # 输出校验报告
    print_validate_report(inconsistent_mods, extra_local_files)

if __name__ == "__main__":
    main()
