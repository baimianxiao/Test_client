# -*- coding: utf-8 -*-

import hashlib
import json
import os

def calculate_file_hash(file_path, hash_algorithm="md5"):
    """
    计算文件哈希值（分块读取，避免大文件内存溢出）
    :param file_path: 文件路径
    :param hash_algorithm: 哈希算法（默认MD5，与分割脚本一致）
    :return: 哈希字符串（失败返回None）
    """
    if not os.path.exists(file_path):
        print(f"[错误] 文件 {file_path} 不存在，无法计算哈希")
        return None

    try:
        hash_obj = hashlib.new(hash_algorithm)
        with open(file_path, 'rb') as f:
            # 4096字节/块读取，平衡效率和内存占用
            while chunk := f.read(4096):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()
    except Exception as e:
        print(f"[错误] 计算 {file_path} 哈希失败：{str(e)}")
        return None


def get_file_size_bytes(file_path):
    """
    获取文件精准字节数（核心校验用）
    :param file_path: 文件路径
    :return: 字节数（失败返回None）
    """
    try:
        return os.path.getsize(file_path)
    except Exception as e:
        print(f"[错误] 获取 {file_path} 大小失败：{str(e)}")
        return None


def get_json_from_file(file_path):
    """
    从JSON文件读取内容
    :param file_path: 文件路径
    :return: JSON对象（失败返回None）
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[错误] 读取 {file_path} 失败：{str(e)}")
        return None

