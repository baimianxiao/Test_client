
import json
from util import *

# 单位转换常量（仅用于展示，所有校验均用字节数）
BYTES_TO_MB = 1024 * 1024



def validate_chunks(chunk_info_list):
    """
    验证分包完整性（仅用字节数校验大小，哈希校验内容）
    :param chunk_info_list: 配置文件中的分包信息列表
    :return: 全部验证通过返回True，否则False
    """
    print("\n--- 开始验证分包完整性 ---")
    all_valid = True
    # 按分包序号排序，确保拼接顺序正确
    sorted_chunks = sorted(chunk_info_list, key=lambda x: x["chunk_index"])

    for chunk in sorted_chunks:
        chunk_path = chunk["chunk_path"]
        expected_hash = chunk["chunk_hash"]
        expected_size = chunk["chunk_size_bytes"]  # 精准字节数

        # 1. 检查分包是否存在
        if not os.path.exists(chunk_path):
            print(f"[失败] 分包缺失：{chunk_path}")
            all_valid = False
            continue

        # 2. 检查分包大小（精准字节数）
        actual_size = get_file_size_bytes(chunk_path)
        if actual_size != expected_size:
            print(f"[失败] 分包大小不匹配：{chunk_path}")
            print(f"       预期：{expected_size} 字节 ({round(expected_size / BYTES_TO_MB, 4)} MB)")
            print(f"       实际：{actual_size} 字节 ({round(actual_size / BYTES_TO_MB, 4)} MB)")
            all_valid = False
            continue

        # 3. 检查分包哈希
        actual_hash = calculate_file_hash(chunk_path)
        if actual_hash != expected_hash:
            print(f"[失败] 分包哈希不匹配：{chunk_path}")
            print(f"       预期：{expected_hash}")
            print(f"       实际：{actual_hash}")
            all_valid = False
            continue

        # 验证通过
        print(f"[成功] 分包验证通过：{chunk_path}")
        print(f"       大小：{actual_size} 字节 ({round(actual_size / BYTES_TO_MB, 4)} MB)")

    if all_valid:
        print("[成功] 所有分包完整性验证通过")
    else:
        print("[失败] 部分分包验证失败，无法还原文件")
    return all_valid


def restore_split_file(file_info, output_dir=None):
    """
    还原被分割的Mod文件
    :param file_info: 配置文件中的单个文件信息（含split_details）
    :param output_dir: 还原文件输出目录（默认原文件目录）
    :return: 还原成功返回True，否则False
    """
    # 基础路径配置
    original_path = file_info["file_path"]
    file_name = os.path.basename(original_path)

    if output_dir is None:
        output_dir = os.path.dirname(original_path)
    os.makedirs(output_dir, exist_ok=True)
    restored_path = os.path.join(output_dir, file_name)

    # 防误覆盖：目标文件已存在则跳过
    if os.path.exists(restored_path):
        print(f"\n[警告] 目标文件已存在：{restored_path}，跳过还原（如需覆盖请先删除）")
        return False

    # 1. 验证分包
    chunk_list = file_info["split_details"]["chunks"]
    if not validate_chunks(chunk_list):
        return False

    # 2. 按序拼接分包
    print(f"\n--- 开始拼接分包，还原文件：{restored_path} ---")
    sorted_chunks = sorted(chunk_list, key=lambda x: x["chunk_index"])
    total_written = 0  # 记录写入总字节数，用于校验

    try:
        with open(restored_path, 'wb') as restored_file:
            for chunk in sorted_chunks:
                chunk_path = chunk["chunk_path"]
                print(f"   拼接：{os.path.basename(chunk_path)}")

                with open(chunk_path, 'rb') as chunk_file:
                    while chunk_data := chunk_file.read(4096):
                        restored_file.write(chunk_data)
                        total_written += len(chunk_data)

        # 3. 校验还原后的文件
        print("\n--- 验证还原文件完整性 ---")
        expected_size = file_info["file_size_bytes"]
        expected_hash = file_info["file_hash"]
        actual_size = get_file_size_bytes(restored_path)
        actual_hash = calculate_file_hash(restored_path)

        # 校验大小（精准字节数）
        if actual_size != expected_size:
            print(f"[失败] 还原文件大小不匹配")
            print(f"       预期：{expected_size} 字节 ({round(expected_size / BYTES_TO_MB, 4)} MB)")
            print(f"       实际：{actual_size} 字节 ({round(actual_size / BYTES_TO_MB, 4)} MB)")
            os.remove(restored_path)  # 删除损坏文件
            print(f"       已删除验证失败的文件：{restored_path}")
            return False

        # 校验哈希
        if actual_hash != expected_hash:
            print(f"[失败] 还原文件哈希不匹配")
            print(f"       预期：{expected_hash}")
            print(f"       实际：{actual_hash}")
            os.remove(restored_path)
            print(f"       已删除验证失败的文件：{restored_path}")
            return False

        # 还原成功
        print(f"[成功] 文件还原完成！")
        print(f"       路径：{restored_path}")
        print(f"       大小：{actual_size} 字节 ({round(actual_size / BYTES_TO_MB, 4)} MB)")
        print(f"       哈希：{actual_hash}")
        return True

    except Exception as e:
        print(f"[错误] 拼接文件失败：{str(e)}")
        # 清理未完成的还原文件
        if os.path.exists(restored_path):
            os.remove(restored_path)
        return False


def validate_unsplit_file(file_info):
    """
    校验未分割的Mod文件（仅验证大小和哈希）
    :param file_info: 配置文件中的单个文件信息
    :return: 校验通过返回True，否则False
    """
    file_path = file_info["file_path"]
    expected_size = file_info["file_size_bytes"]
    expected_hash = file_info["file_hash"]

    print(f"\n--- 校验未分割文件：{file_path} ---")

    # 1. 检查文件是否存在
    if not os.path.exists(file_path):
        print(f"[失败] 文件缺失：{file_path}")
        return False

    # 2. 校验大小（精准字节数）
    actual_size = get_file_size_bytes(file_path)
    if actual_size != expected_size:
        print(f"[失败] 文件大小不匹配")
        print(f"       预期：{expected_size} 字节 ({round(expected_size / BYTES_TO_MB, 4)} MB)")
        print(f"       实际：{actual_size} 字节 ({round(actual_size / BYTES_TO_MB, 4)} MB)")
        return False

    # 3. 校验哈希
    actual_hash = calculate_file_hash(file_path)
    if actual_hash != expected_hash:
        print(f"[失败] 文件哈希不匹配")
        print(f"       预期：{expected_hash}")
        print(f"       实际：{actual_hash}")
        return False

    # 校验通过
    print(f"[成功] 未分割文件校验通过")
    print(f"       大小：{actual_size} 字节 ({round(actual_size / BYTES_TO_MB, 4)} MB)")
    print(f"       哈希：{actual_hash}")
    return True


def main(config_file, output_dir=None):
    """
    主函数：读取配置文件，批量处理所有Mod文件（还原分割文件/校验未分割文件）
    :param config_file: 分割脚本生成的JSON配置文件路径
    :param output_dir: 还原文件输出目录（可选）
    """
    # 1. 验证配置文件存在性
    if not os.path.isfile(config_file):
        print(f"[错误] 配置文件不存在：{config_file}")
        return

    # 2. 读取配置文件
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        print(f"[成功] 读取配置文件：{config_file}")
        print(f"       分割时间：{config['split_time']}")
        print(f"       分割阈值：{config['split_threshold_mb']} MB ")
        print(f"       待处理文件总数：{len(config['all_mod_files'])}")
    except Exception as e:
        print(f"[错误] 读取配置文件失败：{str(e)}")
        return

    # 3. 批量处理所有文件
    stats = {
        "total": len(config["all_mod_files"]),
        "split": 0,  # 分割文件数
        "unsplit": 0,  # 未分割文件数
        "success": 0,  # 处理成功数
        "fail": 0  # 处理失败数
    }

    for file_info in config["all_mod_files"]:
        print("\n==================================================")
        if file_info["is_split"]:
            stats["split"] += 1
            # 处理分割文件（还原）
            result = restore_split_file(file_info, output_dir)
        else:
            stats["unsplit"] += 1
            # 处理未分割文件（校验）
            result = validate_unsplit_file(file_info)

        # 更新统计
        if result:
            stats["success"] += 1
        else:
            stats["fail"] += 1

    # 4. 输出处理总结
    print("\n==================================================")
    print("--- 处理总结 ---")
    print(f"总计文件数：{stats['total']}")
    print(f"分割文件数：{stats['split']}（需还原）")
    print(f"未分割文件数：{stats['unsplit']}（仅校验）")
    print(f"处理成功：{stats['success']} 个")
    print(f"处理失败：{stats['fail']} 个")


if __name__ == "__main__":
    # 命令行参数解析
    #parser = argparse.ArgumentParser(description="MC Mod 分割还原+校验工具（修复大小检测问题）")
    #parser.add_argument("--config-file", "-c", required=True, help="分割生成的JSON配置文件路径（必填）")
    #parser.add_argument("--output-dir", "-o", help="还原文件输出目录（可选，默认原文件目录）")
    #args = parser.parse_args()

    # 执行主函数
    main("config/mod_info.json"
         "", "temp")